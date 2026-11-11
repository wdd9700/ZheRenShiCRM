import baseConfig from './vitest.config.js'
import vueJsx from '@vitejs/plugin-vue-jsx'
import path from 'node:path'

export default {
  ...baseConfig,
  plugins: [...baseConfig.plugins, vueJsx()],
  resolve: {
    ...baseConfig.resolve,
    alias: baseConfig.resolve.alias.map(alias =>
      alias.find instanceof RegExp && alias.find.test('@framework/ui/telemetry')
        ? { find: '@framework/ui', replacement: path.resolve(import.meta.dirname, '../../frappe/ui/src') }
        : alias,
    ),
    dedupe: [
      'vue', 'vue-router', 'frappe-ui', 'reka-ui', '@vueuse/core', 'dompurify',
      'vuedraggable', '@tiptap/core', '@tiptap/pm', '@tiptap/vue-3',
      'prosemirror-model', 'prosemirror-state', 'prosemirror-view',
      'prosemirror-transform', '@codemirror/view', 'marked',
    ],
  },
}
