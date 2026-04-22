import { isTauri } from '@tauri-apps/api/core'

export async function pickDirectory(
  defaultPath: string | null,
): Promise<string | null> {
  if (!isTauri()) {
    return null
  }

  try {
    const { open } = await import('@tauri-apps/plugin-dialog')
    const result = await open({
      directory: true,
      multiple: false,
      defaultPath: defaultPath ?? undefined,
    })

    return typeof result === 'string' ? result : null
  } catch (error) {
    console.error('LinguaSub failed to open the folder picker.', error)
    throw new Error('无法打开文件夹选择窗口，请稍后重试。')
  }
}
