# Octopus Intelligent Go for Home Assistant

Custom Home Assistant integration for Intelligent Octopus Go EV charging.
Internally this uses Kraken's SmartFlex GraphQL API, which is why some developer
notes still reference SmartFlex schema and operation names.

## First release scope

- Target/max charge percentage number entity
- Start immediate charge button
- Cancel immediate charge button
- Current charging/device state sensor
- Current state of charge sensor
- Current vehicle charge limit sensor

The integration signs in once with your Octopus credentials and stores only the
returned refresh token. It auto-selects the first Octopus account and first
compatible Intelligent Go device.

## Manual install

Copy `custom_components/octopus_intelligent_go` into your Home Assistant
`custom_components` directory and restart Home Assistant.

Then add the integration from:

```text
Settings -> Devices & services -> Add integration -> Octopus Intelligent Go
```

## Notes

This uses the unofficial Kraken GraphQL API observed from the Octopus Energy
Android app. See `API.md` for captured operations and future data points.
