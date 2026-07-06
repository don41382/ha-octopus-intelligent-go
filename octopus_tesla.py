#!/usr/bin/env python3
"""Automate Octopus Intelligent Go Tesla charge preferences.

Passwords are never cached. Successful login stores a refresh token in
./.octopus_tesla_auth.json by default so later commands can refresh access.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GRAPHQL_URL = "https://api.oees-kraken.energy/v1/graphql/"
DEFAULT_USER_AGENT = "OctoAppClient/Android/4.134.0 (Android 16; emu64a)"
DEFAULT_AUTH_FILE = ".octopus_tesla_auth.json"

DAYS = [
    "MONDAY",
    "TUESDAY",
    "WEDNESDAY",
    "THURSDAY",
    "FRIDAY",
    "SATURDAY",
    "SUNDAY",
]

LOGIN_MUTATION = """
mutation Login($input: ObtainJSONWebTokenInput!) {
  obtainKrakenToken(input: $input) {
    __typename
    refreshExpiresIn
    refreshToken
    token
  }
}
""".strip()

LONG_LIVED_REFRESH_MUTATION = """
mutation generateLongLivedRefreshToken($input: ObtainLongLivedRefreshTokenInput!) {
  obtainLongLivedRefreshToken(input: $input) {
    __typename
    refreshToken
    refreshExpiresIn
  }
}
""".strip()

GET_ACCOUNT_LIST_QUERY = """
query GetAccountList {
  viewer {
    __typename
    accounts {
      __typename
      number
    }
  }
}
""".strip()

GET_SMART_FLEX_DEVICES_QUERY = """
query GetSmartFlexDevices($accountNumber: String!, $deviceId: String) {
  devices(accountNumber: $accountNumber, deviceId: $deviceId) {
    __typename
    id
    name
    deviceType
    provider
    propertyId
    integrationDeviceId
    status {
      __typename
      current
      isSuspended
    }
    preferences {
      __typename
      gridExport
    }
    ... on SmartFlexVehicle {
      make
    }
  }
}
""".strip()

SET_DEVICE_PREFERENCES_MUTATION = """
mutation SetSmartFlexDevicePreferences($input: SmartFlexDevicePreferencesInput!) {
  setDevicePreferences(input: $input) {
    __typename
    id
    preferences {
      __typename
      targetType
      unit
      mode
      schedules {
        __typename
        dayOfWeek
        time
        min
        max
      }
    }
  }
}
""".strip()

BOOST_CHARGE_MUTATION = """
mutation FlexUpdateBoostCharge($input: UpdateBoostChargeInput!) {
  updateBoostCharge(input: $input) {
    __typename
    id
    provider
    deviceType
  }
}
""".strip()


class KrakenError(RuntimeError):
    pass


@dataclass(frozen=True)
class Auth:
    token: str
    refresh_token: str | None = None
    refresh_expires_in: int | None = None


class KrakenClient:
    def __init__(
        self,
        *,
        graphql_url: str = GRAPHQL_URL,
        user_agent: str = DEFAULT_USER_AGENT,
        proxy: str | None = None,
        flapjack: str | None = None,
        dry_run: bool = False,
    ) -> None:
        self.graphql_url = graphql_url
        self.user_agent = user_agent
        self.flapjack = flapjack
        self.dry_run = dry_run
        handlers: list[urllib.request.BaseHandler] = []
        if proxy:
            handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        self.opener = urllib.request.build_opener(*handlers)

    def graphql(
        self,
        *,
        operation_name: str,
        query: str,
        variables: dict[str, Any],
        token: str | None = None,
        flapjack: bool = False,
    ) -> dict[str, Any]:
        payload = {
            "query": query,
            "operationName": operation_name,
            "variables": variables,
            "extensions": {"clientLibrary": {"name": "apollo-kotlin", "version": "5.0.0"}},
        }
        if self.dry_run:
            print(json.dumps(_redact_payload(payload), indent=2, sort_keys=True))
            return {"dryRun": True}

        body = json.dumps(payload, separators=(",", ":")).encode()
        url = self.graphql_url + "?" + urllib.parse.urlencode({"debug_op_name": operation_name})
        headers = {
            "x-apollo-operation-name": operation_name,
            "accept": "multipart/mixed;deferSpec=20220824, application/graphql-response+json, application/json",
            "accept-language": "en-US",
            "user-agent": self.user_agent,
            "content-type": "application/json",
        }
        if token:
            headers["authorization"] = token
        if flapjack:
            headers["x-kraken-flapjack"] = self.flapjack or secrets.token_hex(32)

        request = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with self.opener.open(request, timeout=30) as response:
                raw = response.read()
                content_type = response.headers.get("content-type", "")
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            detail = _decode_response(raw, exc.headers.get("content-type", ""))
            raise KrakenError(f"HTTP {exc.code}: {json.dumps(detail, indent=2)}") from exc
        except urllib.error.URLError as exc:
            raise KrakenError(f"request failed: {exc.reason}") from exc

        data = _decode_response(raw, content_type)
        if isinstance(data, dict) and data.get("errors"):
            raise KrakenError(json.dumps(data["errors"], indent=2))
        if not isinstance(data, dict):
            raise KrakenError(f"unexpected response: {data!r}")
        return data

    def login_email_password(self, email: str, password: str) -> Auth:
        data = self.graphql(
            operation_name="Login",
            query=LOGIN_MUTATION,
            variables={"input": {"email": email, "password": password}},
            flapjack=True,
        )
        if self.dry_run:
            return Auth(token="<dry-run>")
        token_data = data["data"]["obtainKrakenToken"]
        return Auth(
            token=token_data["token"],
            refresh_token=token_data.get("refreshToken"),
            refresh_expires_in=token_data.get("refreshExpiresIn"),
        )

    def login_refresh_token(self, refresh_token: str) -> Auth:
        data = self.graphql(
            operation_name="Login",
            query=LOGIN_MUTATION,
            variables={"input": {"refreshToken": refresh_token}},
            flapjack=True,
        )
        if self.dry_run:
            return Auth(token="<dry-run>", refresh_token="<dry-run>")
        token_data = data["data"]["obtainKrakenToken"]
        return Auth(
            token=token_data["token"],
            refresh_token=token_data.get("refreshToken"),
            refresh_expires_in=token_data.get("refreshExpiresIn"),
        )

    def login_organization(self, organization_secret_key: str) -> Auth:
        data = self.graphql(
            operation_name="Login",
            query=LOGIN_MUTATION,
            variables={"input": {"organizationSecretKey": organization_secret_key}},
            flapjack=True,
        )
        if self.dry_run:
            return Auth(token="<dry-run>")
        token_data = data["data"]["obtainKrakenToken"]
        return Auth(
            token=token_data["token"],
            refresh_token=token_data.get("refreshToken"),
            refresh_expires_in=token_data.get("refreshExpiresIn"),
        )

    def long_lived_refresh_token(self, *, org_token: str, kraken_token: str) -> dict[str, Any]:
        data = self.graphql(
            operation_name="generateLongLivedRefreshToken",
            query=LONG_LIVED_REFRESH_MUTATION,
            variables={"input": {"krakenToken": kraken_token}},
            token=org_token,
        )
        if self.dry_run:
            return {"refreshToken": "<dry-run>", "refreshExpiresIn": 0}
        return data["data"]["obtainLongLivedRefreshToken"]

    def get_account_numbers(self, *, token: str) -> list[str]:
        data = self.graphql(
            operation_name="GetAccountList",
            query=GET_ACCOUNT_LIST_QUERY,
            variables={},
            token=token,
        )
        if self.dry_run:
            return ["<dry-run-account-number>"]
        accounts = data.get("data", {}).get("viewer", {}).get("accounts") or []
        return [
            account["number"]
            for account in accounts
            if isinstance(account, dict) and isinstance(account.get("number"), str)
        ]

    def get_smart_flex_devices(
        self,
        *,
        token: str,
        account_number: str,
        device_id: str | None = None,
    ) -> list[dict[str, Any]]:
        data = self.graphql(
            operation_name="GetSmartFlexDevices",
            query=GET_SMART_FLEX_DEVICES_QUERY,
            variables={"accountNumber": account_number, "deviceId": device_id},
            token=token,
        )
        if self.dry_run:
            return [
                {
                    "id": "<dry-run-device-id>",
                    "name": "<dry-run-device>",
                    "deviceType": "ELECTRIC_VEHICLE",
                    "provider": "TESLA",
                }
            ]
        devices = data.get("data", {}).get("devices") or []
        return [device for device in devices if isinstance(device, dict)]

    def set_max_percentage(
        self,
        *,
        token: str,
        device_id: str,
        percent: float,
        time: str,
        days: list[str],
    ) -> dict[str, Any]:
        schedules = [{"dayOfWeek": day, "time": time, "max": float(percent)} for day in days]
        return self.graphql(
            operation_name="SetSmartFlexDevicePreferences",
            query=SET_DEVICE_PREFERENCES_MUTATION,
            variables={
                "input": {
                    "deviceId": device_id,
                    "mode": "CHARGE",
                    "unit": "PERCENTAGE",
                    "schedules": schedules,
                }
            },
            token=token,
        )

    def update_boost_charge(self, *, token: str, device_id: str, action: str) -> dict[str, Any]:
        return self.graphql(
            operation_name="FlexUpdateBoostCharge",
            query=BOOST_CHARGE_MUTATION,
            variables={"input": {"deviceId": device_id, "action": action}},
            token=token,
        )


def _decode_response(raw: bytes, content_type: str) -> Any:
    text = raw.decode("utf-8", errors="replace")
    if "multipart/mixed" in content_type:
        return _decode_multipart_json(text, content_type)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise KrakenError(f"response is not JSON: {text[:500]}") from exc


def _decode_multipart_json(text: str, content_type: str) -> Any:
    boundary = ""
    for part in content_type.split(";"):
        part = part.strip()
        if part.startswith("boundary="):
            boundary = part.split("=", 1)[1].strip('"')
            break
    if not boundary:
        raise KrakenError("multipart response did not include a boundary")
    for chunk in text.split("--" + boundary):
        if "\r\n\r\n" in chunk:
            _, body = chunk.split("\r\n\r\n", 1)
        elif "\n\n" in chunk:
            _, body = chunk.split("\n\n", 1)
        else:
            continue
        body = body.strip()
        if body and body != "--":
            return json.loads(body)
    raise KrakenError("multipart response did not include a JSON body")


def _redact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    def redact(value: Any, key: str = "") -> Any:
        lowered = key.lower()
        if lowered in {"password", "token", "refreshtoken", "krakentoken", "organizationsecretkey"}:
            return "<redacted>"
        if isinstance(value, dict):
            return {k: redact(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [redact(v, key) for v in value]
        return value

    return redact(payload)


def _print_result(data: dict[str, Any], *, verbose: bool) -> None:
    if verbose:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print("ok")


def _env_or_arg(value: str | None, env_name: str) -> str | None:
    return value or os.environ.get(env_name)


def _account_number(args: argparse.Namespace, client: KrakenClient, token: str) -> str:
    account_number = _env_or_arg(args.account_number, "OCTOPUS_ACCOUNT_NUMBER")
    if account_number:
        return account_number

    accounts = client.get_account_numbers(token=token)
    if not accounts:
        raise KrakenError("no accounts returned by GetAccountList")
    account_number = accounts[0]
    if not args.dry_run:
        print(f"using account: {account_number}", file=sys.stderr)
    return account_number


def _device_id(args: argparse.Namespace, client: KrakenClient, token: str) -> str:
    device_id = _env_or_arg(args.device_id, "OCTOPUS_DEVICE_ID")
    if device_id:
        return device_id

    account_number = _account_number(args, client, token)
    devices = client.get_smart_flex_devices(token=token, account_number=account_number)
    if not devices:
        raise KrakenError(f"no Intelligent Go devices returned for account {account_number}")
    device = devices[0]
    device_id = device.get("id")
    if not isinstance(device_id, str) or not device_id:
        raise KrakenError("first Intelligent Go device did not include an id")
    if not args.dry_run:
        print(f"using device: {device_id} ({_device_summary(device)})", file=sys.stderr)
    return device_id


def _device_summary(device: dict[str, Any]) -> str:
    parts = [
        str(device.get("name") or "unnamed"),
        str(device.get("deviceType") or "unknown-type"),
        str(device.get("provider") or "unknown-provider"),
    ]
    make = device.get("make")
    if make:
        parts.append(str(make))
    return ", ".join(parts)


def _print_devices(account_number: str, devices: list[dict[str, Any]], *, first_id: bool, verbose: bool) -> None:
    if first_id:
        if not devices:
            raise KrakenError(f"no Intelligent Go devices returned for account {account_number}")
        device_id = devices[0].get("id")
        if not isinstance(device_id, str) or not device_id:
            raise KrakenError("first Intelligent Go device did not include an id")
        print(device_id)
        return

    if verbose:
        print(json.dumps({"accountNumber": account_number, "devices": devices}, indent=2, sort_keys=True))
        return

    print(f"account: {account_number}")
    if not devices:
        print("no Intelligent Go devices found")
        return
    for idx, device in enumerate(devices, start=1):
        marker = "*" if idx == 1 else " "
        device_id = device.get("id") or "<missing-id>"
        print(f"{marker} {idx}. {device_id} ({_device_summary(device)})")


def _parse_days(raw: str) -> list[str]:
    if raw.lower() == "all":
        return DAYS
    aliases = {day[:3]: day for day in DAYS}
    aliases.update({day: day for day in DAYS})
    result = []
    for item in raw.split(","):
        key = item.strip().upper()
        if not key:
            continue
        if key not in aliases:
            raise KrakenError(f"invalid day {item!r}; use all or comma-separated day names")
        result.append(aliases[key])
    if not result:
        raise KrakenError("at least one day is required")
    return result


def _validate_time(value: str) -> str:
    parts = value.split(":")
    if len(parts) != 2:
        raise KrakenError("time must be HH:MM")
    hour, minute = parts
    if not (hour.isdigit() and minute.isdigit()):
        raise KrakenError("time must be HH:MM")
    if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
        raise KrakenError("time must be a valid 24-hour HH:MM value")
    return f"{int(hour):02d}:{int(minute):02d}"


def _token_for(args: argparse.Namespace, client: KrakenClient) -> Auth:
    token = _env_or_arg(args.token, "OCTOPUS_TOKEN")
    if token:
        return Auth(token=token)

    refresh_token = _env_or_arg(args.refresh_token, "OCTOPUS_REFRESH_TOKEN")
    if refresh_token:
        return client.login_refresh_token(refresh_token)

    email = _env_or_arg(args.email, "OCTOPUS_EMAIL")
    password = _env_or_arg(args.password, "OCTOPUS_PASSWORD")
    if email:
        if not password:
            password = getpass.getpass("Octopus password: ")
        return client.login_email_password(email, password)

    cached_refresh_token = _cached_refresh_token(args)
    if cached_refresh_token:
        return client.login_refresh_token(cached_refresh_token)

    raise KrakenError(
        "missing auth: run login first, pass --email, pass --token, "
        "or set OCTOPUS_REFRESH_TOKEN"
    )


def _auth_file(args: argparse.Namespace) -> Path:
    return Path(args.auth_file).expanduser()


def _cached_refresh_token(args: argparse.Namespace) -> str | None:
    if args.no_auth_cache:
        return None
    path = _auth_file(args)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise KrakenError(f"could not read auth cache {path}: {exc}") from exc
    token = data.get("refreshToken") or data.get("refresh_token")
    if token and isinstance(token, str):
        return token
    return None


def _save_auth_cache(args: argparse.Namespace, auth: Auth) -> None:
    if args.dry_run or args.no_auth_cache or not auth.refresh_token:
        return
    path = _auth_file(args)
    payload = {
        "refreshToken": auth.refresh_token,
        "refreshExpiresIn": auth.refresh_expires_in,
    }
    try:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        path.chmod(0o600)
    except OSError as exc:
        raise KrakenError(f"could not write auth cache {path}: {exc}") from exc


def _auth_cache_message(args: argparse.Namespace) -> str:
    if args.no_auth_cache:
        return "auth cache disabled"
    return f"auth cached in {_auth_file(args)}"


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--email", help="Octopus login email, or OCTOPUS_EMAIL")
    common.add_argument("--password", help="Octopus login password, or OCTOPUS_PASSWORD")
    common.add_argument("--token", help="Existing access token, or OCTOPUS_TOKEN")
    common.add_argument("--refresh-token", help="Existing refresh token, or OCTOPUS_REFRESH_TOKEN")
    common.add_argument("--device-id", help="Tesla Intelligent Go device id, or OCTOPUS_DEVICE_ID")
    common.add_argument("--account-number", help="Octopus account number, or OCTOPUS_ACCOUNT_NUMBER")
    common.add_argument("--proxy", default=os.environ.get("OCTOPUS_PROXY"), help="Optional HTTP(S) proxy URL")
    common.add_argument("--flapjack", default=os.environ.get("OCTOPUS_FLAPJACK"), help="Optional captured x-kraken-flapjack value")
    common.add_argument("--auth-file", default=os.environ.get("OCTOPUS_AUTH_FILE", DEFAULT_AUTH_FILE), help="Refresh-token cache file")
    common.add_argument("--no-auth-cache", action="store_true", help="Do not read or write the refresh-token cache")
    common.add_argument("--graphql-url", default=os.environ.get("OCTOPUS_GRAPHQL_URL", GRAPHQL_URL))
    common.add_argument("--user-agent", default=os.environ.get("OCTOPUS_USER_AGENT", DEFAULT_USER_AGENT))
    common.add_argument("--dry-run", action="store_true", help="Print redacted payload instead of sending it")
    common.add_argument("-v", "--verbose", action="store_true", help="Print full JSON response")

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    login = subparsers.add_parser("login", parents=[common], help="Log in and verify credentials")
    login.add_argument("--organization-secret-key", help="Optional org secret, or OCTOPUS_ORG_SECRET_KEY")
    login.add_argument(
        "--long-lived-refresh",
        action="store_true",
        help="Also obtain a long-lived refresh token using the organization token",
    )
    login.add_argument("--print-token", action="store_true", help="Print full access token")
    login.add_argument("--print-refresh-token", action="store_true", help="Print full refresh token")

    devices = subparsers.add_parser("devices", parents=[common], help="List Intelligent Go devices")
    devices.add_argument("--first-id", action="store_true", help="Print only the first device id")

    set_max = subparsers.add_parser("set-max", parents=[common], help="Set max Tesla charge percentage")
    set_max.add_argument("--percent", type=float, required=True, help="Target max percentage, e.g. 69")
    set_max.add_argument("--time", default="07:30", help="Schedule time in HH:MM, default 07:30")
    set_max.add_argument("--days", default="all", help="all or comma-separated days, default all")

    boost = subparsers.add_parser("boost", parents=[common], help="Start immediate Tesla charging")
    boost.set_defaults(boost_action="BOOST")

    cancel = subparsers.add_parser("cancel-boost", parents=[common], help="Cancel immediate Tesla charging")
    cancel.set_defaults(boost_action="CANCEL")

    combo = subparsers.add_parser(
        "set-max-and-boost",
        parents=[common],
        help="Set max percentage, then start immediate Tesla charging",
    )
    combo.add_argument("--percent", type=float, required=True, help="Target max percentage, e.g. 69")
    combo.add_argument("--time", default="07:30", help="Schedule time in HH:MM, default 07:30")
    combo.add_argument("--days", default="all", help="all or comma-separated days, default all")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    client = KrakenClient(
        graphql_url=args.graphql_url,
        user_agent=args.user_agent,
        proxy=args.proxy,
        flapjack=args.flapjack,
        dry_run=args.dry_run,
    )

    try:
        if args.command == "login":
            auth = _token_for(args, client)
            _save_auth_cache(args, auth)
            print("login ok")
            if args.print_token:
                print(auth.token)
            else:
                print(f"access token: {_mask(auth.token)}")
            if auth.refresh_token:
                if args.print_refresh_token:
                    print(f"refresh token: {auth.refresh_token}")
                else:
                    print(f"refresh token: {_mask(auth.refresh_token)}")
                if auth.refresh_expires_in is not None:
                    print(f"refresh expires in: {auth.refresh_expires_in}s")
                print(_auth_cache_message(args))

            org_secret = _env_or_arg(args.organization_secret_key, "OCTOPUS_ORG_SECRET_KEY")
            if args.long_lived_refresh:
                if not org_secret:
                    raise KrakenError(
                        "missing organization secret: pass --organization-secret-key "
                        "or set OCTOPUS_ORG_SECRET_KEY"
                    )
                org_auth = client.login_organization(org_secret)
                long_lived = client.long_lived_refresh_token(
                    org_token=org_auth.token,
                    kraken_token=auth.token,
                )
                if args.print_refresh_token:
                    print(f"long-lived refresh token: {long_lived['refreshToken']}")
                else:
                    print(f"long-lived refresh token: {_mask(long_lived['refreshToken'])}")
                print(f"long-lived refresh expires in: {long_lived['refreshExpiresIn']}s")
            return 0

        auth = _token_for(args, client)
        _save_auth_cache(args, auth)

        if args.command == "devices":
            account_number = _account_number(args, client, auth.token)
            devices = client.get_smart_flex_devices(token=auth.token, account_number=account_number)
            _print_devices(account_number, devices, first_id=args.first_id, verbose=args.verbose)
            return 0

        device_id = _device_id(args, client, auth.token)

        if args.command == "set-max":
            data = client.set_max_percentage(
                token=auth.token,
                device_id=device_id,
                percent=args.percent,
                time=_validate_time(args.time),
                days=_parse_days(args.days),
            )
            _print_result(data, verbose=args.verbose)
            return 0

        if args.command == "boost":
            data = client.update_boost_charge(token=auth.token, device_id=device_id, action="BOOST")
            _print_result(data, verbose=args.verbose)
            return 0

        if args.command == "cancel-boost":
            data = client.update_boost_charge(token=auth.token, device_id=device_id, action="CANCEL")
            _print_result(data, verbose=args.verbose)
            return 0

        if args.command == "set-max-and-boost":
            preferences = client.set_max_percentage(
                token=auth.token,
                device_id=device_id,
                percent=args.percent,
                time=_validate_time(args.time),
                days=_parse_days(args.days),
            )
            boost = client.update_boost_charge(token=auth.token, device_id=device_id, action="BOOST")
            if args.verbose:
                print(json.dumps({"setMax": preferences, "boost": boost}, indent=2, sort_keys=True))
            else:
                print("ok")
            return 0

        parser.error(f"unknown command {args.command!r}")
        return 2
    except KrakenError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _mask(value: str, visible: int = 8) -> str:
    if len(value) <= visible * 2:
        return "<redacted>"
    return f"{value[:visible]}...{value[-visible:]}"


if __name__ == "__main__":
    raise SystemExit(main())
