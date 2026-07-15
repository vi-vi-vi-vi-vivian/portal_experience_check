Object.defineProperty(navigator, "webdriver", { get: () => undefined });
Object.defineProperty(navigator, "languages", { get: () => ["en-US", "en"] });
Object.defineProperty(navigator, "plugins", { get: () => [1, 2, 3, 4, 5] });

window.chrome = window.chrome || { runtime: {} };

const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
if (originalQuery) {
  window.navigator.permissions.query = (parameters) => (
    parameters && parameters.name === "notifications"
      ? Promise.resolve({ state: Notification.permission })
      : originalQuery(parameters)
  );
}
