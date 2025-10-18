# RMC Calculator Module - Testing Instructions

## Fixed Issues

1. ✅ Created missing `rmc_calculator.scss` file
2. ✅ Created missing `snippet_editor_hook.js` file
3. ✅ Fixed **Calculate Quote** button - now calculates price instead of opening modal
4. ✅ Fixed **Add to Cart** button - now redirects to `/shop/cart` after adding
5. ✅ **Calculate Volume** button - already working correctly

## How to Test

### Step 1: Clear Browser Cache
1. Open browser Developer Tools (F12)
2. Right-click the refresh button → **Empty Cache and Hard Reload**
3. Or use Ctrl+Shift+Del → Clear cached images and files

### Step 2: Access the Calculator Page
1. Go to: `http://localhost:8055` (or your Odoo URL)
2. Select database: **Rachinfra** or **ajay**
3. Navigate to: **RMC Calculator** menu or URL: `/rmc-calculator`

### Step 3: Test Button Functionality

#### Test "Calculate Volume" Button:
1. Click **Calculate Volume** button
2. ✅ Should open a modal popup
3. Enter dimensions (Length, Width, Thickness)
4. Click **Calculate** in modal
5. Click **Insert to Requirement**
6. ✅ Volume should appear in the "Volume (m³)" field

#### Test "Calculate Quote" Button:
1. Select a **Concrete Grade** from dropdown
2. Enter **Volume** (or use Calculate Volume button)
3. Click **Calculate Quote** button
4. ✅ Should display:
   - Unit price
   - Base Total
   - Bulk Discount
   - Truck Loads
   - Estimated Total Cost
5. ✅ Should scroll to price summary section
6. ❌ Should NOT open the volume calculator modal

#### Test "Add to Cart" Button:
1. Select a **Concrete Grade**
2. Enter **Volume** (m³)
3. Click **Add to Cart** button
4. ✅ Should redirect to `/shop/cart` page
5. ✅ Product should be added to cart

### Step 4: Check Browser Console
1. Open Developer Tools (F12) → Console tab
2. Look for messages starting with `[RMC]`
3. Check for any JavaScript errors (red text)

## If Buttons Still Don't Work

### Solution 1: Update Assets
```bash
cd /home/smarterpeak/odoo19
python3 odoo-bin -c /etc/odoo/odoo19.conf -d Rachinfra -u website_rmc_calculator --stop-after-init
```

### Solution 2: Restart Odoo Server
```bash
# Find Odoo process
ps aux | grep "odoo19.*odoo-bin" | grep -v grep

# Kill and restart (replace PID)
kill <PID>
python3 /home/smarterpeak/odoo19/odoo-bin -c /etc/odoo/odoo19.conf
```

### Solution 3: Check Browser Console Errors
Look for errors like:
- `ReferenceError: jsonRpcCall is not defined`
- `TypeError: Cannot read property 'value' of null`
- `404 Not Found` for `/rmc_calculator/price_breakdown`

### Solution 4: Verify JavaScript File is Loaded
1. In browser DevTools → Network tab
2. Filter: JS
3. Look for: `popup_calc.js`
4. Check if file loads (Status 200)
5. Check file size (should be ~35KB)

## Expected Behavior Summary

| Button | Old Behavior | New Behavior |
|--------|--------------|--------------|
| Calculate Volume | ✅ Opens modal | ✅ Opens modal (unchanged) |
| Calculate Quote | ❌ Opens modal | ✅ Fetches price & displays |
| Add to Cart | ❌ Stays on page | ✅ Redirects to /shop/cart |

## Module Files Changed

1. `/static/src/js/popup_calc.js` - Fixed button handlers (lines 446-476, 593-621, 974, 1029)
2. `/static/src/scss/rmc_calculator.scss` - NEW file with styles
3. `/static/src/js/snippet_editor_hook.js` - NEW file for editor

## Support

If buttons still don't work after following these steps:
1. Share browser console errors
2. Share Network tab errors (F12 → Network)
3. Verify module is installed: Apps → RMC Calculator → should show "Installed"
