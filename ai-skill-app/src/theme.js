const THEME_KEY = 'theme'

export function getTheme() {
  return localStorage.getItem(THEME_KEY) === 'dark' ? 'dark' : 'light'
}

export function applyTheme(theme) {
  document.documentElement.dataset.theme = theme
  localStorage.setItem(THEME_KEY, theme)
}

export function toggleTheme() {
  const next = getTheme() === 'dark' ? 'light' : 'dark'
  applyTheme(next)
  return next
}
