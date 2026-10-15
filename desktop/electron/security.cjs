const prefixes = [
  "/dashboard",
  "/records/",
  "/ingest",
  "/dataset/import",
  "/feedback",
  "/reviews/",
  "/preferences/",
  "/calendar",
  "/conflicts",
  "/proposals/",
  "/imports/",
  "/prompts/",
  "/summary",
  "/marks/",
  "/settings",
  "/connections",
  "/models",
  "/updates",
  "/notifications/",
  "/profile/",
];
function validateRequest(request) {
  if (
    !request ||
    !["GET", "POST", "PUT", "DELETE", "PATCH"].includes(request.method || "GET")
  )
    throw Error("Unsupported request");
  const path = request.path;
  if (
    typeof path !== "string" ||
    !path.startsWith("/") ||
    path.startsWith("//") ||
    path.includes("\\") ||
    decodeURIComponent(path).includes("..") ||
    !prefixes.some(
      (p) =>
        path === p ||
        path.startsWith(p.endsWith("/") ? p : p + "/") ||
        path.startsWith(p + "?"),
    )
  )
    throw Error("Request outside application API");
  if (request.body && JSON.stringify(request.body).length > 2_500_000)
    throw Error("Request too large");
  return { ...request, method: request.method || "GET" };
}
function safeExternal(value) {
  const url = new URL(value);
  if (
    !["https:", "http:"].includes(url.protocol) ||
    url.username ||
    url.password
  )
    throw Error("Only web links are allowed");
  return url.href;
}
module.exports = { validateRequest, safeExternal };
