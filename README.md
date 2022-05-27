Insert a tour into the OneZoom database with:

```
curl -X PUT -H "Content-Type: application/json" --user admin \
    http://.../tour/custom.json/edge_species.json \
    -d @/srv/devel/onezoom-tours/edge_species.json
```

Once uploaded you can trigger a tour manually in the javascript console with:

```
onezoom.controller.tour_start('/tour/custom/edge_species')
```
