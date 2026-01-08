# bt_asset_management — Stage-1 Enhancement Specification

## A) Enhancement Scope Summary
- Extend the existing standalone asset master (`bt.asset`) with system-generated codes, custodianship, operational status, analytical cost tracking, and optional one-to-one links to Maintenance Equipment and Fleet Vehicle, keeping current fields and flows intact.
- Introduce category-level code patterns and quantity-based asset splitting while preserving manual asset codes and current single-asset records; no accounting or depreciation logic is added or modified.
- All changes are layered as incremental enhancements within the existing module; no refactor, module split, or accounting touchpoints.

## B) Model-wise Enhancement Map
### 1) bt.asset
- **New fields**: system-generated `asset_code` flag/fields to track auto/manual origin; many2one `custodian_id` to `res.partner` (responsible person); status selection expanded to `active`, `idle`, `breakdown`, `disposed`; analytical cost fields (e.g., acquisition cost, maintenance cost totals, computed total cost—analytical only); quantity input (`qty_requested`) for split and a computed/helper `qty_split` indicator; optional one2one-style many2one links to `maintenance.equipment` and `fleet.vehicle` stored on the asset, read-only after set.
- **Constraints**: unique `asset_code` across assets; enforce one asset per linked maintenance equipment or fleet vehicle; disallow setting both disposed state and active location inconsistently; prevent zero/negative quantities when splitting.
- **Computed/helpers**: auto-assign `asset_code` on create based on category pattern when empty; helper method to generate split records from quantity while copying category/location; compute analytical total cost as sum of cost components.

### 2) bt.asset.category
- **Additions**: fields for code pattern/sequence prefix and padding, and a boolean to require auto-code; optional sequence relation if needed for category-specific numbering.

### 3) bt.asset.move
- **Additions**: no change to move mechanics; optionally include analytical cost memo field if needed for future reporting (read-only, no accounting effect). If not required, moves remain unchanged.

## C) Enhancement Flows (WORDS ONLY)
- **Asset code generation**: On asset create, if `asset_code` absent, system builds a unique code using the selected category’s pattern/sequence; stored code becomes read-only after creation and must remain unique. Manual codes are accepted but also enforced unique.
- **Quantity-based split**: When a user enters a quantity >1 on asset creation, the system generates individual asset records (one per physical unit) copying shared details (category, location, custodian, costs) and assigns unique auto-codes per unit; original quantity field is used only for the split process, not persisted as an ongoing counter.
- **Operational linkage**: Asset may optionally reference exactly one maintenance equipment or fleet vehicle. Links are read-only once set and do not create or update records in those modules; they are used only for visibility/reporting.
- **Status lifecycle**: Status selection expands to include idle, breakdown, and disposed alongside active. Disposed status is used without accounting impact; status changes are tracked via chatter and do not alter depreciation or create moves automatically (scrap move remains explicit).
- **Cost intelligence (analytical)**: Analytical cost fields are captured on the asset (e.g., purchase/acquisition, maintenance, other). A computed total provides reporting insight only—no journal entries, no integration with `account.asset` or `account.move`.

## D) Backward Compatibility Rules
- Existing assets remain valid with their current manual `asset_code` values; new uniqueness checks respect existing non-blank codes and only prevent future duplicates.
- If no new fields are used, assets behave as before: manual codes allowed, current location/move logic unchanged, scrapping still via moves.
- Auto-code applies only when creating new assets without an explicit code; category patterns do not modify historical records. Maintenance/fleet links and cost fields are optional and nullable to avoid impacting old data.

## E) Security & Access Impact (High-Level)
- Existing `group_asset_management_user` access is sufficient; new fields inherit model permissions. No new groups required unless later segregation proves necessary.

## F) Task Breakdown (Critical)
1. **TASK-01 (NEW)** — Implement category-based auto-code scaffolding: add category pattern/sequence fields and uniqueness constraint on `bt.asset` codes; adjust asset create helper to assign codes when missing; update views to expose pattern fields (models: `bt.asset`, `bt.asset.category`; views/data: asset/category forms, sequence if needed). Dependency: none.
2. **TASK-02 (NEW)** — Quantity-based split flow: add transient/helper logic to split requested quantity into individual assets at creation with shared attributes and unique codes; add quantity input on asset form; ensure validation for positive quantity (models: `bt.asset`; views: asset form). Depends on TASK-01 for code generation.
3. **TASK-03 (PATCH)** — Custodian and operational status extension: add custodian field and extend status selection; ensure disposed status interacts safely with location/scrap logic; update views and chatter tracking (models: `bt.asset`; views: asset form/list/kanban). Independent but should apply after TASK-02 for consistent forms.
4. **TASK-04 (NEW)** — Maintenance/Fleet linkage: add optional many2one fields to `maintenance.equipment` and `fleet.vehicle`, enforce one-to-one via constraints, display read-only once set; add to asset views (models: `bt.asset`; views: asset form/search). Independent but may follow TASK-03 for view consolidation.
5. **TASK-05 (PATCH)** — Analytical cost fields: introduce read-only/reporting cost components and computed total on assets; add to forms and search/reporting views; ensure no accounting hooks (models: `bt.asset`; views: asset form/list/search). Independent.
6. **TASK-06 (PATCH/Optional)** — Move-level memo for analytical tracking: if desired, add optional note/cost memo on `bt.asset.move` for reporting only; minor view update (models: `bt.asset.move`; views: move form/list). Independent.

Stage-1 Enhancement Spec complete.
Ready to proceed to Stage-2 Task Execution.
