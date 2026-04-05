import { translations } from '../i18n/translations'
import useLanguageStore from '../store/useLanguageStore'

export function useTranslation() {
  const { language } = useLanguageStore()
  
  const t = (key) => {
    return translations[language]?.[key] || translations['fr'][key] || key
  }

  return { t, language }
}
