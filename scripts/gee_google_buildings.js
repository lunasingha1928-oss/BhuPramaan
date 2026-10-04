// Google Earth Engine Code Editor script (https://code.earthengine.google.com)
// Exports REAL Google data for the T. Nagar study area to your Google Drive:
//   1. Google Open Buildings v3 polygons            -> google_open_buildings_tnagar.geojson
//   2. Open Buildings 2.5D Temporal, two years      -> google_temporal_2016.tif, google_temporal_2023.tif
// Then copy the files into C:\sih26013\data\real\ and rerun scripts\build_real.py.
//
// Paste into a new script, press Run, then open the Tasks tab (top right) and click RUN on each export.

var bbox = ee.Geometry.Rectangle([80.2330, 13.0380, 80.2430, 13.0480]);   // west, south, east, north
Map.centerObject(bbox, 16);
Map.addLayer(bbox, {color: 'red'}, 'study area', false);

// ---- 1. building polygons
var polys = ee.FeatureCollection('GOOGLE/Research/open-buildings/v3/polygons').filterBounds(bbox);
print('Google Open Buildings polygons in the area:', polys.size());
Map.addLayer(polys, {color: '1baf7a'}, 'Google Open Buildings');
Export.table.toDrive({
  collection: polys.select(['confidence', 'area_in_meters', 'full_plus_code']),
  description: 'google_open_buildings_tnagar',
  fileFormat: 'GeoJSON'
});

// ---- 2. temporal building presence and height (4 m grid, yearly)
var temporal = ee.ImageCollection('GOOGLE/Research/open-buildings-temporal/v1').filterBounds(bbox);
print('Temporal bands:', temporal.first().bandNames());
[2016, 2023].forEach(function (year) {
  var img = temporal
    .filter(ee.Filter.calendarRange(year, year, 'year'))
    .mosaic()
    .select(['building_presence', 'building_height'])
    .clip(bbox)
    .toFloat();
  Map.addLayer(img.select('building_presence'), {min: 0, max: 1}, 'presence ' + year, false);
  Export.image.toDrive({
    image: img,
    description: 'google_temporal_' + year,
    region: bbox,
    scale: 4,
    crs: 'EPSG:32644',
    maxPixels: 1e9
  });
});
// If a dataset ID or band name has changed, the Console will say so; search the Earth Engine
// catalog for "Open Buildings" and update the two IDs above.
