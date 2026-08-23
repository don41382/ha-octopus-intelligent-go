# Octopus Intelligent Go

Custom Home Assistant integration for Intelligent Octopus Go EV charging.

This integration lets Home Assistant read and control the charging preferences
exposed by Octopus Energy's mobile app, including target charge percentage and
immediate charging.

## Features

- Set the target charge percentage
- Start or stop immediate charging with one action button
- Read the current charging/device state
- Read the current vehicle state of charge
- Read the current vehicle charge limit

## Requirements

- Home Assistant 2026.7 or newer
- An Octopus Energy account with Intelligent Octopus Go configured
- A compatible vehicle or charger already linked in the Octopus Energy app

## Installation

### HACS Custom Repository

1. Open HACS in Home Assistant.
2. Open the three-dot menu and choose **Custom repositories**.
3. Add this repository:

   ```text
   https://github.com/don41382/ha-octopus-intelligent-go
   ```

4. Select **Integration** as the category.
5. Install **Octopus Intelligent Go**.
6. Restart Home Assistant.

### Manual Install

Copy the integration directory into your Home Assistant config directory:

```text
custom_components/octopus_intelligent_go
```

The final path should be:

```text
/config/custom_components/octopus_intelligent_go
```

Restart Home Assistant after copying the files.

## Setup

Add the integration from:

```text
Settings -> Devices & services -> Add integration -> Octopus Intelligent Go
```

Sign in with the same email and password used at the
[Octopus Energy Spain account portal](https://octopusenergy.es/login). The
password is used only for that login and is not stored. Home Assistant retrieves
and stores the account's Developer API key and Kraken refresh token in the config
entry. Normal token rotation is serialized so concurrent entity updates cannot
invalidate each other, and the API key is used automatically if a refresh token
expires.

Existing installations automatically capture and retain the API key during the
next successful update, as long as their current refresh token is still valid.
If an installation is already asking for authentication, open the integration's
**Reconfigure** action and sign in once with the Spanish account credentials.
Do not use the UK login at `auth.octopus.energy`; Spanish customer accounts use
the separate `octopusenergy.es` login.

The first setup version automatically selects the first Octopus account and the
first compatible Intelligent Go device returned by the API.

## Entities

| Entity | Type | Description |
| --- | --- | --- |
| Target charge percentage | Number | Sets the desired maximum charge percentage |
| Start/Stop Immediate | Button | Shows Start Immediate or Stop Immediate depending on current state |
| State | Sensor | Current charging state |
| State of charge | Sensor | Current vehicle battery percentage |
| Vehicle charge limit | Sensor | Current vehicle-side charge limit |

## Automation Services

For automations, use the deterministic services instead of the smart button:

```yaml
action: octopus_intelligent_go.start_immediate_charge
data:
  device_id: YOUR_HOME_ASSISTANT_DEVICE_ID
```

```yaml
action: octopus_intelligent_go.cancel_immediate_charge
data:
  device_id: YOUR_HOME_ASSISTANT_DEVICE_ID
```

The `device_id` is the Home Assistant device registry ID selected by the
automation UI. Raw Kraken/SmartFlex device IDs are also accepted in YAML.

## Troubleshooting

After installing or updating, restart Home Assistant. If the integration icon is
missing, hard-refresh the browser or clear Home Assistant's frontend cache.

Immediate charging can fail if Octopus reports that the vehicle is unplugged or
not at home. In that case, the service error should include the refusal reason
returned by Kraken.

## Disclaimer

This integration can change charging preferences and start or stop immediate
charging. Use it at your own risk.

The project is provided without warranty. The maintainers are not responsible
for charging costs, missed charging schedules, vehicle or charger behavior,
battery impact, account issues, service interruptions, or any other problems
caused directly or indirectly by using this integration.

## Notes

This is an unofficial integration and is not affiliated with Octopus Energy.
It uses Kraken's private GraphQL API observed from the Octopus Energy Android
app. That API can change without notice.

Developer notes for captured GraphQL operations and future data points are in
[API.md](API.md). The public integration is named Octopus Intelligent Go, but
some API internals still use Kraken's `SmartFlex` naming.
