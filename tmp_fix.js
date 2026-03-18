const fs = require('fs');

const content = fs.readFileSync('src/features/feed/components/subscription-form/NotificationSection.tsx', 'utf8');

// Add import for fetchRuntimeConfig
let newContent = content.replace(
  "import { useTranslation } from '@/hooks/useTranslation'",
  "import { useTranslation } from '@/hooks/useTranslation'\nimport { fetchRuntimeConfig } from '@/lib/runtime-config'"
);

// Add import for useEffect and useCallback
newContent = newContent.replace(
  "import { useMemo, useState } from 'react'",
  "import { useMemo, useState, useEffect, useCallback } from 'react'"
);

// Add types and constants before export function
const typesAndConsts = `
interface BindGroupStep {
  title: string
  hint?: string
}

interface BindGroupConfig {
  variables?: Record<string, string>
  steps: BindGroupStep[]
}

const defaultBindConfig: BindGroupConfig = {
  variables: {
    botName: '机器人',
    featureName: '智能群助手'
  },
  steps: [
    { title: '添加{{botName}}到群聊', hint: '打开群设置 → {{featureName}} → 添加机器人 → 搜索并添加{{botName}}' },
    { title: '点击开始绑定', hint: '' },
    { title: '在群聊中 @{{botName}} 发送消息', hint: '' },
  ]
}

// Replace template variables like {{botName}} with actual values
const replaceVariables = (text: string, variables: Record<string, string>): string => {
  return text.replace(/\\{\\{(\\w+)\\}\\}/g, (_, key) => variables[key] || '{{' + key + '}}')
}
`;

newContent = newContent.replace(
  'type BindingState',
  typesAndConsts + '\ntype BindingState'
);

fs.writeFileSync('src/features/feed/components/subscription-form/NotificationSection.tsx', newContent);
console.log('Part 1 done');
