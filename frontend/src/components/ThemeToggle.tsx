import { Moon, Sun } from 'lucide-react'

import { useThemeStore } from '@/store/theme-store'

export function ThemeToggle() {
  const theme = useThemeStore((state) => state.theme)
  const toggle = useThemeStore((state) => state.toggle)

  return (
    <button
      type="button"
      onClick={toggle}
      className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 sm:p-2 dark:text-slate-400 dark:hover:bg-slate-800"
      aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      {theme === 'dark' ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
    </button>
  )
}
