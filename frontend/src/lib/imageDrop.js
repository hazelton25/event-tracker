// Figure out what kind of image was dragged onto the page: a real file
// (dragged out of a folder / Finder / Explorer) or a web image (dragged out
// of a browser tab, which usually arrives as a URL or an <img> tag rather
// than a File).
export function extractDroppedImage(dataTransfer) {
  if (!dataTransfer) return null;

  if (dataTransfer.files && dataTransfer.files.length > 0) {
    const file = dataTransfer.files[0];
    if (file.type.startsWith("image/")) {
      return { type: "file", file };
    }
  }

  const uri = (
    dataTransfer.getData("text/uri-list") || dataTransfer.getData("text/plain")
  ).trim();
  if (/^https?:\/\//i.test(uri)) {
    return { type: "url", url: uri };
  }

  const html = dataTransfer.getData("text/html");
  if (html) {
    const m = html.match(/<img[^>]+src=["']([^"']+)["']/i);
    if (m) return { type: "url", url: m[1] };
  }

  return null;
}
