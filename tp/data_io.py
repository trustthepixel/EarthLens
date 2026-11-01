from tp.attacks import BANDS


def export_geotiff(chip, row, path):
    # Export a chip as a georeferenced GeoTIFF that can be opened in GIS software.
    import rasterio
    from rasterio.transform import Affine
    tr = Affine(10.0, 0.0, float(row['x0']), 0.0, -10.0, float(row['y0']))
    with rasterio.open(path, 'w', driver='GTiff', height=chip.shape[1], width=chip.shape[2], count=chip.shape[0],
                       dtype=str(chip.dtype), crs=f"EPSG:{int(row['epsg'])}", transform=tr, compress='deflate') as dst:
        dst.write(chip)
        if chip.shape[0] == len(BANDS):
            dst.descriptions = tuple(BANDS)
