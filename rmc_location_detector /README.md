# RMC Location Detector

Website enhancement for Odoo 19 that detects the visitor city and postal code, dynamically assigns the right pricelist, and keeps checkout totals consistent with the shipping address.

## Features
- Hybrid location flow: GeoIP guess, optional browser GPS lookup, and manual override dialog.
- City/ZIP mapping to product pricelists with longest ZIP prefix priority and website scoping.
- Session pricelist switching with cart repricing and checkout synchronization banner.
- Responsive header chip and modal UI with accessible Owl templates.

## Configuration
1. Enable the module and open *Website ⟶ Configuration ⟶ Settings*.
2. In **Website Location Detection**, toggle IP/GPS detection and adjust the cookie lifetime.
3. Provide a Google Maps API key or Mapbox access token (GPS prefers Google if both are set).
4. Define **Location Zones** under *Website ⟶ Configuration ⟶ Location Zones*: set a city or ZIP prefix and assign a pricelist.

## Usage Notes
- The header chip reflects the active location; click **Change** to edit manually or use GPS.
- Checkout ZIP changes call the backend to lock prices and display a confirmation banner when repricing occurs.
- Cookies (`ri_loc_city`, `ri_loc_zip`, `ri_loc_method`, `ri_loc_updated`) honour the configured lifetime.

## Privacy
Location data is stored on the transient website visitor record only. No partner addresses are modified, and external geocoding uses the keys you configure.
