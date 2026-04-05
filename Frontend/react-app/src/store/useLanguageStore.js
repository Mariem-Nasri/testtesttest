import { create } from 'zustand'

const useLanguageStore = create((set, get) => ({
  language: localStorage.getItem('app-language') || 'fr',
  
  setLanguage: (lang) => {
    localStorage.setItem('app-language', lang)
    set({ language: lang })
  },
  
  toggleLanguage: () => {
    const current = get().language
    const newLang = current === 'fr' ? 'en' : 'fr'
    localStorage.setItem('app-language', newLang)
    set({ language: newLang })
  },
}))

export default useLanguageStore
