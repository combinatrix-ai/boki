// The website puts the landing page one level above the docs; point the logo there from every page.
document.addEventListener("DOMContentLoaded", () => {
  const root = document.documentElement.dataset.content_root || "./";
  document.querySelectorAll("a.navbar-brand").forEach((a) => { a.href = root + "../"; });
});
