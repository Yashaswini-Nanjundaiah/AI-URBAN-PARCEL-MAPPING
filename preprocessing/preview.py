from preprocessing.display import render_image_preview


def write_preview(image_path, output_path, max_size=2048):
    """Write a browser-ready preview and return its metadata.

    Returns a dict with ``path`` and ``overlay_bounds`` so the caller
    can store the geographic extent that Leaflet needs.
    """
    result = render_image_preview(image_path, output_path, max_size=max_size)
    return result
