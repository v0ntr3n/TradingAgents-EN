/**
 * Front-end configuration tool
 */

/**
 * Detect whether it is JD Cloud cooperation version mode
 * Controlled by the environment variable VITE_JDYUN_MODE injected at build time
 */
export const isJdyunMode = (): boolean => {
  return import.meta.env.VITE_JDYUN_MODE === 'true'
}

/**
 * JD Cloud dialogue model list (default value)
 *
 * 🔥 When running, it will be backend `/api/config/jdyun/status` The returned available_models override,
 * Avoid inconsistency between the front-end hard-coded model list and the back-end OPENAI_MODEL environment variable.
 */
export let JDYUN_CHAT_MODELS: string[] = [
  'GLM-5',
  'GLM-5.1',
  'GLM-5.2',
  'DeepSeek-V4-Flash',
]

let _jdyunModelsLoaded = false

/**
 * Load the list of JD Cloud available models from the backend (called once during startup/initialization)
 *
 * In JD Cloud mode, the model list is based on the back-end OPENAI_MODEL environment variable (comma separated).
 * The front end only needs to call this function when the page is initialized to be consistent with the back end.
 * Return to the default list in non-JD Cloud mode or when loading fails.
 */
export const loadJdyunChatModels = async (): Promise<string[]> => {
  if (!isJdyunMode() || _jdyunModelsLoaded) return JDYUN_CHAT_MODELS
  try {
    // Dynamic import breaks circular dependencies:config -> request -> auth -> config
    const { ApiClient } = await import('@/api/request')
    const resp: any = await ApiClient.get('/api/config/jdyun/status', undefined, { skipErrorHandler: true })
    const data = resp?.data || resp
    const models = data?.available_models
    if (Array.isArray(models) && models.length > 0) {
      JDYUN_CHAT_MODELS = models
    }
  } catch (e) {
    console.warn('Failed to load JD Cloud model list, use default list:', e)
  } finally {
    _jdyunModelsLoaded = true
  }
  return JDYUN_CHAT_MODELS
}

/**
 * Get a list of available models
 * Returns the preset model in JD Cloud mode, returns null in non-JD Cloud mode (indicating the model configured using the database)
 */
export const getAvailableModels = (): string[] | null => {
  if (isJdyunMode()) {
    return [...JDYUN_CHAT_MODELS]
  }
  return null
}
