# Migration Parity Tracker

Source of truth: `app.py`
Target: modular Doobie-powered app

## Must preserve before replacing `app.py`

### Global platform behavior
- [ ] Auth flow (admin, user, trial)
- [ ] Theme toggle
- [ ] Upload logging / admin upload viewer
- [ ] Daily upload persistence
- [ ] AI provider debug/admin tools where still relevant
- [ ] Doobie-only routing replacing legacy AI paths

### Buyer Operations workspace
- [ ] Inventory Dashboard full parity
- [ ] Target DOH settings
- [ ] Velocity adjustment
- [ ] Sales period controls
- [ ] Category DOS quick table
- [ ] Forecast table
- [ ] Product-level rows toggle
- [ ] SKU Inventory Buyer View tabs
- [ ] Export Forecast Table (Excel)
- [ ] AI Inventory Check replaced by Doobie

### Trends workspace
- [ ] Category mix
- [ ] Package size mix
- [ ] Top movers by SKU
- [ ] Best sellers by category
- [ ] Fast movers + low stock

### Delivery Impact workspace
- [ ] Manifest upload
- [ ] Sales upload
- [ ] Before/after analysis
- [ ] Same weekday WoW analysis
- [ ] KPI summary table
- [ ] Plotly charting
- [ ] Top delivered items by lift
- [ ] Unmatched item review
- [ ] PDF debug text dump

### Slow Movers workspace
- [ ] Full filter bar
- [ ] Velocity window selector
- [ ] DOH threshold controls
- [ ] Top N selector
- [ ] Search / category / brand filters
- [ ] KPI strip
- [ ] Decision-first table
- [ ] Discount tier summary
- [ ] Excel export

### PO Builder workspace
- [ ] Reorder cross-reference from Inventory Dashboard
- [ ] Add all reorder ASAP lines
- [ ] Manual PO entry form
- [ ] Inventory cross-check in line items
- [ ] Totals and taxes
- [ ] PDF generation
- [ ] Smart PO merged without removing original capabilities

### Compliance workspace
- [ ] Compliance source upload
- [ ] Template download
- [ ] Grounded Q&A
- [ ] Admin compliance QA tools

### Buyer Intelligence workspace
- [ ] KPI summary
- [ ] Category and SKU risk tables
- [ ] AI Buyer Brief replaced by Doobie while preserving section outputs

### Extraction Command Center workspace
- [ ] Executive Overview
- [ ] Run Analytics
- [ ] Toll Processing
- [ ] Compliance / METRC
- [ ] Data Input
- [ ] AI Ops Brief replaced by Doobie
- [ ] Manual run entry preserved
- [ ] Manual toll job entry preserved

## Current truth
The modular app has improved structure and Doobie integration, but it is not yet at full feature parity with `app.py`. Do not replace `app.py` until every checklist item above is completed or intentionally retired with an equivalent replacement.
