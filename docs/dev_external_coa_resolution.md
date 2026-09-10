# DEV external COA resolution boundary

Real Massachusetts COAs attached to DEV Sandbox lots are read-only tested-material reference evidence. Label Studio may display their laboratory, test date, cannabinoid/terpene totals, and analyte results only when all of these are true:

- organization slug is `dev-sandbox`
- facility code is `SANDBOX`
- lot quality state is passing
- evidence source is `coa:dev_ma_external_reference` or `inherited:dev_ma_external_reference`
- COA is parsed with verification state `external_reference`
- the COA has a real source METRC identifier

The lot's current `compliance_package_id` remains the label/QR regulatory identity. The external COA source tag is never promoted to the current package identity and is never evidence for a provider write.
