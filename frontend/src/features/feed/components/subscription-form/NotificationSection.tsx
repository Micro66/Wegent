'use client'

// SPDX-FileCopyrightText: 2025 Weibo, Inc.
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Notification Section - Notification level, channels, and webhooks
 * Simplified version: binding management moved to /settings/integrations
 */

import { Bell, ExternalLink } from 'lucide-react'
import { useMemo, useCallback } from 'react'
import { useRouter } from 'next/navigation'

import { CollapsibleSection } from '@/components/common/CollapsibleSection'
import { Label } from '@/components/ui/label'
import { Button } from '@/components/ui/button'
import { useTranslation } from '@/hooks/useTranslation'
import type { NotificationChannelBindingConfig, NotificationLevel } from '@/types/subscription'
import type { NotificationSectionProps } from './types'
import { NotificationChannelCard } from './notification-section/NotificationChannelCard'
import { NotificationLevelSelector } from './notification-section/NotificationLevelSelector'
import { WebhookListEditor } from './notification-section/WebhookListEditor'

const levelOptionFallbacks: Record<NotificationLevel, { label: string; description: string }> = {
  silent: {
    label: '静默',
    description: '执行但不在时间线显示',
  },
  default: {
    label: '默认',
    description: '在动态时间线中显示',
  },
  notify: {
    label: '通知',
    description: '通过 Messager 渠道发送通知',
  },
}

// Paths to settings page
const SETTINGS_PATH = '/settings?section=integrations&tab=integrations'

export function NotificationSection({
  devNotificationLevel,
  setDevNotificationLevel,
  devNotificationChannels,
  setDevNotificationChannels,
  devAvailableChannels,
  devSettingsLoading,
  notificationWebhooks,
  setNotificationWebhooks,
  channelBindingConfigs,
  setChannelBindingConfigs,
}: NotificationSectionProps) {
  const { t } = useTranslation('feed')
  const router = useRouter()

  const levelOptions = useMemo(
    () =>
      (['silent', 'default', 'notify'] as NotificationLevel[]).map(level => ({
        value: level,
        label: t(`notification_level.${level}`, levelOptionFallbacks[level].label),
        description: t(
          `notification_settings.level_${level}_desc`,
          levelOptionFallbacks[level].description
        ),
      })),
    [t]
  )

  const getBindingConfig = useCallback(
    (channelId: number) =>
      channelBindingConfigs.find(
        (cfg: NotificationChannelBindingConfig) => cfg.channel_id === channelId
      ) ?? {
        channel_id: channelId,
        bind_private: true,
        bind_group: false,
      },
    [channelBindingConfigs]
  )

  const getPrivateBound = useCallback(
    (channelId: number) => {
      const channel = devAvailableChannels.find(item => item.id === channelId)
      return Boolean(channel?.is_bound)
    },
    [devAvailableChannels]
  )

  const getGroupBound = useCallback(
    (channelId: number) => {
      const config = getBindingConfig(channelId)
      return Boolean(config.group_conversation_id)
    },
    [getBindingConfig]
  )

  const navigateToSettings = useCallback(() => {
    router.push(SETTINGS_PATH)
  }, [router])

  const updateBindingConfig = useCallback(
    (
      channelId: number,
      updater: (prev: { bind_private: boolean; bind_group: boolean }) => {
        bind_private: boolean
        bind_group: boolean
      }
    ) => {
      setChannelBindingConfigs((prev: NotificationChannelBindingConfig[]) => {
        const existing = prev.find(
          (cfg: NotificationChannelBindingConfig) => cfg.channel_id === channelId
        ) ?? {
          channel_id: channelId,
          bind_private: true,
          bind_group: false,
        }
        const next = updater({
          bind_private: existing.bind_private,
          bind_group: existing.bind_group,
        })
        const rest = prev.filter(
          (cfg: NotificationChannelBindingConfig) => cfg.channel_id !== channelId
        )
        return [...rest, { ...existing, ...next }]
      })
    },
    [setChannelBindingConfigs]
  )

  return (
    <CollapsibleSection
      title={t('notification_settings.title', '通知设置')}
      icon={<Bell className="h-4 w-4 text-primary" />}
      defaultOpen={true}
    >
      <div className="space-y-4">
        <NotificationLevelSelector
          label={t('notification_settings.level_label', '通知级别')}
          value={devNotificationLevel}
          options={levelOptions}
          disabled={devSettingsLoading}
          onChange={setDevNotificationLevel}
        />

        {devNotificationLevel === 'notify' && (
          <section className="space-y-4 rounded-xl border border-border bg-surface/40 p-4">
            <div className="space-y-1">
              <Label className="text-sm font-medium">
                {t('notification_settings.channels_label', '通知渠道')}
              </Label>
              <p className="text-xs text-text-muted">选择要接收即时通知的渠道</p>
            </div>

            {devAvailableChannels.length > 0 ? (
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {devAvailableChannels.map(channel => (
                  <NotificationChannelCard
                    key={channel.id}
                    channel={channel}
                    selected={devNotificationChannels.includes(channel.id)}
                    disabled={devSettingsLoading}
                    onToggle={() => {
                      setDevNotificationChannels(prev =>
                        prev.includes(channel.id)
                          ? prev.filter(id => id !== channel.id)
                          : [...prev, channel.id]
                      )
                    }}
                  />
                ))}
              </div>
            ) : (
              <div className="rounded-lg border border-dashed border-border bg-background px-4 py-5">
                <p className="text-xs text-text-muted">
                  {t('notification_settings.no_channels', '暂无可用的 Messager 渠道')}
                </p>
              </div>
            )}

            {devNotificationChannels.length > 0 && (
              <div className="space-y-3" data-testid="notification-channel-config-section">
                <div className="flex items-center justify-between">
                  <div className="space-y-1">
                    <Label className="text-sm font-medium">渠道投递配置</Label>
                    <p className="text-xs text-text-muted">配置已选渠道的通知投递目标</p>
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={navigateToSettings}
                    className="gap-1"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                    去绑定渠道
                  </Button>
                </div>

                {devNotificationChannels.map(channelId => {
                  const channel = devAvailableChannels.find(c => c.id === channelId)
                  if (!channel) return null

                  const config = getBindingConfig(channelId)
                  const privateBound = getPrivateBound(channelId)
                  const groupBound = getGroupBound(channelId)

                  return (
                    <div
                      key={channelId}
                      className="rounded-lg border border-border bg-background p-4 space-y-3"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-medium">{channel.name}</span>
                        <span className="text-xs text-text-muted">
                          {channel.channel_type === 'dingtalk' ? '钉钉' : channel.channel_type}
                        </span>
                      </div>

                      <div className="space-y-2">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="text-sm">私聊投递</span>
                            {privateBound ? (
                              <span className="text-xs text-success">已绑定</span>
                            ) : (
                              <span className="text-xs text-warning">未绑定</span>
                            )}
                          </div>
                          <input
                            type="checkbox"
                            checked={config.bind_private}
                            onChange={e =>
                              updateBindingConfig(channelId, prev => ({
                                ...prev,
                                bind_private: e.target.checked,
                              }))
                            }
                            className="rounded border-border"
                          />
                        </div>

                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <span className="text-sm">群聊投递</span>
                            {groupBound ? (
                              <span className="text-xs text-success">
                                已绑定: {config.group_name || '群组'}
                              </span>
                            ) : (
                              <span className="text-xs text-warning">未绑定</span>
                            )}
                          </div>
                          <input
                            type="checkbox"
                            checked={config.bind_group}
                            disabled={!groupBound}
                            onChange={e =>
                              updateBindingConfig(channelId, prev => ({
                                ...prev,
                                bind_group: e.target.checked,
                              }))
                            }
                            className="rounded border-border"
                          />
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </section>
        )}

        <WebhookListEditor
          notificationWebhooks={notificationWebhooks}
          setNotificationWebhooks={setNotificationWebhooks}
        />

        {devSettingsLoading && <p className="text-xs text-text-muted">{t('common:loading')}</p>}
      </div>
    </CollapsibleSection>
  )
}
