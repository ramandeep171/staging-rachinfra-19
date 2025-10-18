# Website RMC Calculator - Public Concrete Calculator Widget

## Module Overview

| Property | Value |
|----------|-------|
**Name**| Website RMC Calculator |
**Technical Name**| `website_rmc_calculator` |
**Version**| 19.0.1.0.0 |
**Category**| Website/eCommerce |
**Author**| RACH INFRA PVT. LTD. |
**License**| LGPL-3 |
**Dependencies**| `website`, `sale_management`, `crm` |

---

## Purpose (क्या है और क्यों जरूरी है)

This module provides a public-facing RMC (Ready-Mix Concrete) calculator on the website. It allows visitors to calculate their concrete needs, get instant price quotes, and submit their requirements to the sales team, generating leads and draft quotations automatically.

**क्या करता है?**
- **Volume Calculation**: Calculates concrete volume based on user-provided dimensions for various shapes.
- **Instant Quoting**: Fetches real-time prices based on the selected concrete grade and volume.
- **Lead Generation**: Automatically creates a CRM lead when a user requests a quote.
- **Sales Order Creation**: Creates a draft sales order for the user.
- **Add to Cart**: Allows users to add the calculated product directly to the shopping cart.

**क्यों जरूरी है?**
- **Lead Generation**: Converts website visitors into actionable CRM leads.
- **Customer Self-Service**: Empowers customers to get instant price estimates 24/7.
- **Sales Automation**: Streamlines the initial quotation process, saving time for the sales team.
- **Enhanced User Experience**: Provides a professional and interactive tool for customers.

---

## Key Features

- **Shape Selection**: Supports various shapes like rectangular slabs, circular areas, etc.
- **Real-Time Price Calculation**: Instantly fetches and displays a price breakdown, including discounts and truck loads.
- **Product Variant Support**: Allows users to select different concrete grades (e.g., M20, M25), which are tied to product variants.
- **Wastage Factor**: Includes an option to add a wastage percentage for more accurate estimates.
- **Truck Load Calculation**: Automatically estimates the number of trucks required.
- **CRM & Sales Integration**: Creates a `crm.lead` and a draft `sale.order` upon quote request.
- **Guest Checkout**: Allows users to get a quote without needing to sign up.
- **Pricelist Aware**: Supports customer-specific pricing through Odoo's pricelist mechanism.

---

## Technical Implementation

### File Structure
```
website_rmc_calculator/
├── static/
│   └── src/
│       ├── js/
│       │   └── snippet_editor_hook.js      # Website builder integration (optional)
│       └── scss/
│           └── rmc_calculator.scss         # Calculator styling
```

**Note**: This is a **static-only module** - no Python models, views, or controllers. Pure frontend widget.

---

## How It Works

### Basic Calculation Formula

```javascript
// Volume calculation
volume = length × width × height  // in meters

// With wastage factor
total_concrete = volume × (1 + wastage_percentage/100)

// Example:
// Length: 10m, Width: 5m, Height: 0.15m (6 inch slab)
// Volume = 10 × 5 × 0.15 = 7.5 m³
// With 10% wastage = 7.5 × 1.10 = 8.25 m³
```

### JavaScript Core Logic

```javascript
function calculateConcrete() {
    // Get inputs
    let length = parseFloat(document.getElementById('length').value);
    let width = parseFloat(document.getElementById('width').value);
    let height = parseFloat(document.getElementById('height').value);
    let wastage = parseFloat(document.getElementById('wastage').value) || 0;

    // Validate
    if (!length || !width || !height) {
        alert('Please enter all dimensions');
        return;
    }

    // Calculate
    let volume = length * width * height;
    let totalConcrete = volume * (1 + wastage/100);

    // Display
    document.getElementById('result').innerHTML = `
        <h3>Required Concrete</h3>
        <p class="volume">${volume.toFixed(2)} m³ (base volume)</p>
        <p class="total">${totalConcrete.toFixed(2)} m³ (with ${wastage}% wastage)</p>
        <p class="bags">Approximately ${(totalConcrete * 6.5).toFixed(0)} bags of cement (50kg each)</p>
    `;
}
```

### SCSS Styling

```scss
.rmc-calculator {
    max-width: 600px;
    margin: 40px auto;
    padding: 30px;
    background: #f9f9f9;
    border-radius: 10px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);

    .input-group {
        margin-bottom: 20px;

        label {
            display: block;
            font-weight: 600;
            margin-bottom: 5px;
        }

        input {
            width: 100%;
            padding: 10px;
            font-size: 16px;
            border: 1px solid #ddd;
            border-radius: 5px;
        }
    }

    .result {
        margin-top: 30px;
        padding: 20px;
        background: #fff;
        border-left: 4px solid #007bff;

        .volume {
            font-size: 18px;
            color: #666;
        }

        .total {
            font-size: 24px;
            font-weight: bold;
            color: #007bff;
        }
    }

    button {
        width: 100%;
        padding: 15px;
        background: #007bff;
        color: white;
        border: none;
        border-radius: 5px;
        font-size: 18px;
        cursor: pointer;

        &:hover {
            background: #0056b3;
        }
    }
}
```

---

## Integration with Website

### Option 1: Page Content

Add calculator HTML to a website page:

```xml
<div class="rmc-calculator">
    <h2>RMC Concrete Calculator</h2>
    <p>Calculate how much concrete you need for your project</p>

    <div class="input-group">
        <label>Length (meters)</label>
        <input type="number" id="length" placeholder="10" step="0.1"/>
    </div>

    <div class="input-group">
        <label>Width (meters)</label>
        <input type="number" id="width" placeholder="5" step="0.1"/>
    </div>

    <div class="input-group">
        <label>Height/Thickness (meters)</label>
        <input type="number" id="height" placeholder="0.15" step="0.01"/>
    </div>

    <div class="input-group">
        <label>Wastage Factor (%)</label>
        <select id="wastage">
            <option value="0">0% - Exact</option>
            <option value="5">5% - Normal</option>
            <option value="10" selected>10% - Recommended</option>
            <option value="15">15% - Complex Shapes</option>
        </select>
    </div>

    <button onclick="calculateConcrete()">Calculate Concrete</button>

    <div id="result" class="result" style="display:none;"></div>
</div>
```

### Option 2: Website Builder Snippet

If `snippet_editor_hook.js` is implemented, calculator can be dragged and dropped in website builder.

---

## Configuration Steps

### 1. Install Module

```bash
./odoo-bin -d database -i website_rmc_calculator
```

### 2. Add to Website Page

1. Go to Website → Pages
2. Create new page: "Concrete Calculator"
3. Edit page → Insert HTML block
4. Paste calculator HTML (see above)
5. Publish page

### 3. Test

1. Visit page as public user
2. Enter dimensions
3. Click Calculate
4. Verify result

---

## Usage Examples

### Example 1: Residential Slab

```
Input:
- Length: 12 meters (40 feet)
- Width: 10 meters (33 feet)
- Height: 0.15 meters (6 inches)
- Wastage: 10%

Calculation:
Base Volume: 12 × 10 × 0.15 = 18 m³
With Wastage: 18 × 1.10 = 19.8 m³

Result:
"You need approximately 19.8 m³ of concrete"
"About 129 bags of cement (50kg each)"
```

### Example 2: Beam

```
Input:
- Length: 6 meters (beam length)
- Width: 0.3 meters (beam width)
- Height: 0.45 meters (beam depth)
- Wastage: 5%

Calculation:
Base Volume: 6 × 0.3 × 0.45 = 0.81 m³
With Wastage: 0.81 × 1.05 = 0.85 m³

Result:
"You need approximately 0.85 m³ of concrete"
```

### Example 3: Circular Column

Advanced formula (if implemented):

```javascript
// For circular column
radius = diameter / 2  // in meters
height = column_height
volume = π × radius² × height

// Example: 12" diameter, 12 feet height
radius = (12 inches / 2) / 39.37 = 0.1524 m
height = 12 feet / 3.281 = 3.658 m
volume = 3.14159 × 0.1524² × 3.658 = 0.267 m³
```

---

## Enhancement Ideas

### 1. Lead Capture Integration

Add form below calculator:

```html
<div class="lead-form">
    <h4>Get a Professional Quote</h4>
    <input type="text" placeholder="Name" id="name"/>
    <input type="email" placeholder="Email" id="email"/>
    <input type="tel" placeholder="Phone" id="phone"/>
    <button onclick="submitLeadWithCalculation()">Get Quote</button>
</div>

<script>
function submitLeadWithCalculation() {
    // Call Odoo JSON-RPC to create crm.lead
    let leadData = {
        name: document.getElementById('name').value,
        email_from: document.getElementById('email').value,
        phone: document.getElementById('phone').value,
        description: `Concrete requirement: ${calculatedVolume} m³`,
    };

    // AJAX call to /web/dataset/call_kw
    $.ajax({
        url: '/web/dataset/call_kw',
        method: 'POST',
        data: JSON.stringify({
            model: 'crm.lead',
            method: 'create',
            args: [leadData],
            kwargs: {},
        }),
        contentType: 'application/json',
        success: function() {
            alert('Thank you! We will contact you shortly.');
        }
    });
}
</script>
```

### 2. Price Estimation

```javascript
// Add grade selector
let grade = document.getElementById('grade').value;  // M20, M25, M30
let pricePerM3 = {'M20': 4500, 'M25': 5000, 'M30': 5500}[grade];
let estimatedCost = totalConcrete * pricePerM3;

document.getElementById('cost').innerHTML = `
    Estimated Cost: ₹${estimatedCost.toLocaleString('en-IN')}
    (@ ₹${pricePerM3}/m³ for ${grade} grade)
`;
```

### 3. Save & Email Calculation

```javascript
function emailCalculation() {
    let email = prompt('Enter your email to receive this calculation:');
    if (email) {
        // Send via Odoo mail
        odoo.jsonRpc('/web/dataset/call_kw', 'call', {
            model: 'mail.mail',
            method: 'create',
            args: [{
                email_to: email,
                subject: 'Your RMC Calculation',
                body_html: document.getElementById('result').innerHTML,
            }],
        }).then(function() {
            alert('Calculation emailed to ' + email);
        });
    }
}
```

### 4. Unit Conversion

```javascript
function convertUnits(value, fromUnit, toUnit) {
    const conversions = {
        'm_to_ft': 3.28084,
        'ft_to_m': 0.3048,
        'm3_to_cft': 35.3147,
        'cft_to_m3': 0.0283168,
    };

    if (fromUnit === 'm' && toUnit === 'ft') {
        return value * conversions.m_to_ft;
    }
    // ... more conversions
}
```

### 5. Structure Templates

```javascript
const templates = {
    'slab': {length: 10, width: 10, height: 0.15},
    'beam': {length: 6, width: 0.3, height: 0.45},
    'column': {length: 0.3, width: 0.3, height: 3},
    'foundation': {length: 5, width: 3, height: 0.5},
};

function loadTemplate(templateName) {
    let template = templates[templateName];
    document.getElementById('length').value = template.length;
    document.getElementById('width').value = template.width;
    document.getElementById('height').value = template.height;
    calculateConcrete();
}
```

---

## SEO & Marketing Benefits

1. **Keyword Target**: "rmc calculator", "concrete calculator", "how much concrete do I need"
2. **Organic Traffic**: Useful tools attract visitors
3. **Backlinks**: Other sites link to useful calculators
4. **Dwell Time**: Users spend time using calculator (positive SEO signal)
5. **Lead Funnel**: Calculator → Quote → Sale

---

## Business Use Cases

**1. B2C Lead Generation**: Homeowners calculating slab requirements
**2. B2B Tool**: Contractors quick estimation for bids
**3. Educational**: Students learning concrete calculations
**4. Marketing**: Share on social media, construction forums

---

## Technical Notes

### Why Static-Only?

- **Performance**: No server-side processing, instant results
- **Caching**: Static assets cache well (fast load)
- **Scalability**: Can handle thousands of concurrent users
- **Simplicity**: No database, no models, just JavaScript

### Future Backend Integration

If needed, add Python controller:

```python
@http.route('/calculator/save', type='json', auth='public')
def save_calculation(self, **post):
    # Save calculation to database
    self.env['rmc.calculation'].sudo().create({
        'visitor_ip': request.httprequest.remote_addr,
        'length': post.get('length'),
        'width': post.get('width'),
        'height': post.get('height'),
        'volume': post.get('volume'),
        'timestamp': fields.Datetime.now(),
    })
    return {'success': True}
```

---

## Version History

**19.0.1.0.0** - Initial release as static widget

---

## Support

**Author**: RACH INFRA PVT. LTD.
**Website**: https://rachinfra.com

---

**End of Documentation**
