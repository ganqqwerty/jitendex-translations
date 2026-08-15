(() => {
  const toggle = document.querySelector('.theme-toggle');
  if (!toggle) return;
  const icon = toggle.querySelector('span');
  const systemTheme = window.matchMedia('(prefers-color-scheme: dark)');
  const themeColor = document.querySelector('meta[name="theme-color"]');

  const isDark = () => document.documentElement.dataset.theme
    ? document.documentElement.dataset.theme === 'dark'
    : systemTheme.matches;

  const sync = () => {
    const dark = isDark();
    const label = dark ? 'Включить светлую тему' : 'Включить тёмную тему';
    toggle.setAttribute('aria-label', label);
    toggle.setAttribute('aria-pressed', String(dark));
    toggle.title = label;
    icon.textContent = dark ? '☀' : '☾';
    if (themeColor) themeColor.content = dark ? '#151411' : '#e8462a';
  };

  toggle.addEventListener('click', () => {
    document.documentElement.dataset.theme = isDark() ? 'light' : 'dark';
    sync();
  });
  systemTheme.addEventListener('change', sync);
  sync();
})();
