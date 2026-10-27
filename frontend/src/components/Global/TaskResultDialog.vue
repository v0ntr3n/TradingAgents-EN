<template>
  <el-dialog v-model="visible" title="Task results" width="60%">
    <div v-if="result">
      <h4>Suggestions</h4>
      <div class="markdown-content" v-html="renderMarkdown(result.recommendation || 'None')"></div>
      <h4 style="margin-top: 16px;">Summary</h4>
      <div class="markdown-content" v-html="renderMarkdown(result.summary || 'None')"></div>
    </div>
    <template #footer>
      <el-button @click="emit('close')">close</el-button>
      <el-button type="primary" @click="emit('view-report')">View report details</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { renderMarkdown as safeMarkdown } from '@/utils/markdown'

const props = defineProps<{ modelValue: boolean; result: any }>()
const emit = defineEmits(['update:modelValue','close','view-report'])

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v)
})

// marked The configuration has been @/utils/markdown Unified management
const renderMarkdown = (s: string) => { try { return safeMarkdown(s||'') } catch { return s } }
</script>

