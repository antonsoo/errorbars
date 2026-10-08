/** The light/dark toggle shared by every page. The choice is the only thing a page stores. */
export function initTheme(button: HTMLButtonElement): void {
  let stored: string | null = null;
  try { stored = localStorage.getItem("errorbars-theme"); } catch { /* Theme remains session-only. */ }
  let dark = stored === "dark" || (stored !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  function apply(): void {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    button.setAttribute("aria-label", dark ? "Switch to light theme" : "Switch to dark theme");
    button.textContent = dark ? "☀" : "☾";
  }
  apply();
  button.addEventListener("click", () => {
    dark = !dark;
    apply();
    try { localStorage.setItem("errorbars-theme", dark ? "dark" : "light"); } catch { /* Optional preference. */ }
  });
}
