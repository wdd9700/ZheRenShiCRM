import baseConfig from './vitest.config.js'
import vueJsx from '@vitejs/plugin-vue-jsx'

export default {
  ...baseConfig,
  plugins: [...baseConfig.plugins, vueJsx()],
}
