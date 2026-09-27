# Existing customer sensor networks

The supported adapters read existing customer accounts. They are not generic RF decoders and do not make Growlink, Aranet base stations or every LoRaWAN device automatically compatible. No equipment commands, downlinks or arbitrary broker/URL configuration are exposed.

## Operator flow

Settings -> Integrations -> Cultivation integrations -> Connect your existing sensor network. Choose Aranet Cloud or The Things Stack, enter the customer-owned key and review the returned sensors. Confirm each selected room, optional zone and supported measurement. DoobieLogic creates canonical devices, sensors and effective-dated room mappings; preview values are not imported as history.

A network connection begins disabled. Successful account discovery is not proof of a working sensor feed. After explicit approval, the host must save a new reading before reporting Receiving. Pausing or replacing a key preserves measurements and mappings. Replacing a key pauses collection and requires fresh discovery and confirmation. No credential is stored in browser query caches, displayed in receipts or passed on the child-process command line.

## Aranet Cloud

Uses the official GET-only API with an ApiKey header scoped to one workspace. Sensor IDs, metric definitions and unit IDs come from that account, including the key creator's unit preferences. Explicitly supported units are normalized; unknown units and changed unit definitions block or quarantine instead of being guessed. The adapter polls selected sensors' latest readings and preserves their source timestamps.

The source API offers history, but this adapter does not yet implement gap backfill. Missed intermediate measurements are not reconstructed from the next latest value. Existing Aranet Cloud access and API entitlement are customer prerequisites; DoobieLogic does not purchase a subscription.

Primary documentation: https://help.aranet.com/aranet-cloud-page/aranet-cloud-landing-page/integrations-and-extensions/cloud-api and the public schema at https://aranet.cloud/api/openapi.yaml. The reviewed schema was saved privately with its SHA-256; fixture tests use the published response structure, not invented sensor unit enums.

## The Things Stack / The Things Network

The current cloud adapter supports reviewed eu1, nam1 and au1 deployments, using a fixed approved registry and regional TLS MQTT endpoint. The customer provides an existing application ID and a key authorized to list its devices and read uplinks. Discovery lists devices, then listens temporarily for actual supported standardized measurements before the operator can approve a sensor.

MQTT is version 3.1.1, TLS port 8883, subscribe-only QoS 0. No publish or downlink function exists in the worker. Uplinks are checked against the selected application, topic and device identity. Only one standardized sample per message is supported initially. Multi-sample or arbitrary vendor decoded payloads require a separately reviewed profile; a device list alone never establishes support.

Air temperature, relative humidity and CO2, plus substrate temperature and electrical conductivity, have explicit standardized contracts. Relative soil moisture is not treated as calibrated VWC. Lux is not PPFD, and a cumulative water meter is not an irrigation event. The dS/m-to-mS/cm conversion is explicit and tested. Vendor receipt time is labeled separately from a normalized sensor timestamp. Explicitly simulated messages cannot become live evidence.

Primary documentation: https://www.thethingsindustries.com/docs/integrations/other-integrations/mqtt/ , https://www.thethingsindustries.com/docs/api/concepts/fieldmasks/ , and https://www.thethingsindustries.com/docs/integrations/payload-formatters/javascript/uplink/ . QoS 0 does not guarantee offline replay. The network's Storage API is a separate batch/history integration, not a substitute for live monitoring.
