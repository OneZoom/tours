# OneZoom Tours

Tour JSON documents that can be inserted into an instance's database.

The JSON format is described in https://github.com/OneZoom/OZtree/blob/main/controllers/tour.py

## Inserting a tour

Insert a tour into the OneZoom database with:

```
curl -X PUT -H "Content-Type: application/json" --user admin \
    http://.../tour/data.json/edge_species \
    -d @edge_species.json
```

## Playing a tour

Once uploaded you can trigger a tour manually in the javascript console with:

```
onezoom.controller.tour_start('/tour/data.html/edge_species')
```

Or trigger it on load (although be warned that autoplaying will not trigger before a click):

```
/life?tour=/tour/data.html/superpowers
```

## Other documentation

HTML tour syntax (what the JSON is converted to): https://github.com/OneZoom/OZtree/blob/main/OZprivate/rawJS/OZTreeModule/src/tour/Tour.js
Extended HTML tour syntax in the relevant handler plugins: https://github.com/OneZoom/OZtree/tree/main/OZprivate/rawJS/OZTreeModule/src/tour/handler
Pinpoints describing locations on the tree: https://github.com/OneZoom/OZtree/blob/main/OZprivate/rawJS/OZTreeModule/src/navigation/pinpoint.js
URLs, including all attributes that can be set in the querystring: https://github.com/OneZoom/OZtree/blob/main/OZprivate/rawJS/OZTreeModule/src/navigation/state.js
Additional documentation on highlights: https://github.com/OneZoom/OZtree/blob/main/OZprivate/rawJS/OZTreeModule/src/projection/highlight/highlight.js
