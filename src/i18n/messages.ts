export type UiLanguage = 'zh' | 'en'

export const UI_LANGUAGE_STORAGE_KEY = 'linguasub-ui-language'

const zhMessages = {
  common: {
    appName: 'LinguaSub',
    currentStage: '当前阶段',
    taskStatus: '任务状态',
    language: {
      label: '界面语言',
      zh: '中文',
      en: 'English',
    },
    buttons: {
      previousStep: '上一步',
      importToContinue: '导入后继续',
      openTranslationSetup: '进入翻译设置',
      startTranslation: '开始翻译',
      working: '处理中...',
      openExport: '进入导出',
      exporting: '导出中...',
      exportSrt: '导出 SRT',
      reloadConfig: '重新加载配置',
      translateAgain: '重新翻译',
      useAutoName: '使用默认名称',
      saveChanges: '保存修改',
      retranslate: '重新翻译',
      retranslating: '重新翻译中...',
      reloadStartupCheck: '重新检查',
      importFile: '导入文件',
      inspecting: '检测中...',
      uninstallLinguaSub: '卸载 LinguaSub',
      uninstalling: '正在启动卸载...',
      downloadModel: '下载模型',
      downloadingModel: '正在下载模型...',
    },
    outputModes: {
      bilingual: '双语',
      single: '单语',
    },
    statuses: {
      idle: '空闲',
      transcribing: '识别中',
      translating: '翻译中',
      exporting: '导出中',
      done: '完成',
      error: '错误',
    },
    runtimeModes: {
      development: '开发版',
      release: '发布版',
    },
    availability: {
      ready: '已就绪',
      missing: '缺失',
      blocked: '受阻',
      needsDependencies: '缺少本地依赖',
      available: '可用',
      downloading: '下载中',
      unavailable: '不可用',
      error: '错误',
    },
    providers: {
      openaiCompatible: 'OpenAI 兼容接口',
      deepseek: 'DeepSeek',
    },
    workflowSteps: {
      Video: '视频',
      Audio: '音频',
      SRT: 'SRT',
      Recognition: '识别',
      Translation: '翻译',
      Export: '导出',
    },
    summary: {
      file: '文件',
      path: '路径',
      route: '流程',
      status: '状态',
      sourceFile: '源文件',
      currentFile: '当前文件',
      projectStatus: '项目状态',
      outputMode: '输出模式',
      translatedSegments: '已翻译片段',
      translatedRows: '已翻译行',
      subtitleRows: '字幕条数',
      livePreviewEdits: '预览修改',
      filteredRows: '筛选结果',
      lastRun: '上次任务',
      nextStage: '下一阶段',
      type: '类型',
      name: '名称',
      translatedCount: '已翻译数量',
      mode: '运行模式',
      backend: '后端状态',
      configPath: '配置路径',
      recommendedUserData: '推荐用户数据目录',
      speechModelFolder: '语音模型目录',
      mediaWorkflow: '媒体工作流',
      srtWorkflow: 'SRT 工作流',
      selectedAsrModel: '识别模型',
      translationConfig: '翻译配置',
      destinationFolder: '保存目录',
      resolvedFileName: '最终文件名',
      exportFormat: '导出格式',
      exportStatus: '导出状态',
      subtitlePackage: '字幕包',
      lastExport: '上次导出',
    },
    placeholders: {
      searchSubtitle: '搜索原文或译文',
      importPath: 'D:\\media\\demo.srt',
      model: 'gpt-4.1-mini',
    },
    misc: {
      loading: '加载中...',
      loadingConfig: '正在加载配置',
      notRecorded: '暂无记录',
      notSelected: '未选择',
      waiting: '等待中',
      notExported: '尚未导出',
      readyToExportAgain: '可以再次导出',
      writingFile: '正在写入文件...',
      notExportedYet: '尚未导出',
      configured: '已配置',
      missing: '未配置',
      includedInExport: '将随导出一起生效',
      alreadySaved: '已保存',
      noSaveRecordedYet: '尚未记录保存',
      noProjectLoaded: '尚未载入项目',
      noImportedFile: '尚未导入文件',
      nothingToPreview: '还没有可预览内容',
      noSegmentsAvailable: '当前没有字幕片段',
      noMatchesFound: '没有匹配结果',
      configUnavailable: '配置不可用',
      waitingForEnvironmentReport: '正在等待环境报告',
      startupCheckPassed: '启动检查通过',
      startupCheckFailed: '启动检查失败',
      importFailed: '导入失败',
      exportFailed: '导出失败',
      translationFlowFailed: '翻译流程失败',
      configError: '配置错误',
      noSubtitleContent: '没有字幕内容',
      missingTranslatedLines: '存在空白译文',
      timelineNeedsAttention: '时间轴需要检查',
      lastExportCompleted: '最近一次导出已完成',
      searchSubtitles: '搜索字幕',
      showing: '当前显示',
      editState: '编辑状态',
      unsavedChanges: '有未保存修改',
      saved: '已保存',
      sourceText: '原文',
      translatedText: '译文',
      provider: '服务商',
      model: '模型',
      baseUrl: 'Base URL',
      apiKey: 'API Key',
      currentRoute: '当前流程',
      preparedSegments: '已准备片段',
      supportedInput: '支持输入',
      import: '导入',
      source: '来源',
      progress: '进度',
      preview: '预览',
      segments: '字幕片段',
      export: '导出',
      summary: '摘要',
      workflow: '流程',
      backend: '后端',
      environment: '环境',
      translation: '翻译',
      unknown: '未知',
      srtSubtitle: 'SRT 字幕',
      video: '视频',
      audio: '音频',
    },
  },
  sidebar: {
    eyebrow: 'Windows 桌面工作流',
    description: '字幕生成与导出工具',
    items: {
      import: {
        label: '导入',
        description: '选择视频、音频或字幕文件',
      },
      recognition: {
        label: '识别',
        description: '准备 faster-whisper 参数',
      },
      translation: {
        label: '翻译',
        description: '选择服务商、模型和输出模式',
      },
      preview: {
        label: '预览',
        description: '检查原文与译文',
      },
      export: {
        label: '导出',
        description: '生成 SRT 输出',
      },
      settings: {
        label: '设置',
        description: '管理服务商和默认项',
      },
    },
    ariaLabel: '主流程导航',
  },
  stepHeader: {
    step: (current: number, total: number) => `步骤 ${current}/${total}`,
  },
  app: {
    workspace: {
      import: {
        title: '导入源文件',
        description: '从本地视频、音频或 SRT 开始。LinguaSub 会自动识别文件类型，并准备正确的处理流程。',
      },
      translation: {
        title: '翻译设置',
        description:
          '选择翻译服务商、模型和输出模式。LinguaSub 会先从识别结果或 SRT 解析结果准备字幕片段，再发送到翻译服务。',
      },
      preview: {
        title: '字幕预览',
        description: '检查翻译结果。当前项目状态中的每条字幕片段都同时包含原文和译文。',
      },
      export: {
        title: '导出字幕',
        description: '根据当前项目状态生成最终字幕文件，支持双语或单语 SRT。',
      },
      settings: {
        title: '应用设置',
        description: '查看当前界面语言与翻译配置，并可从这里启动 Windows 卸载流程。',
      },
    },
    labels: {
      supportedInputHint: '支持 MP4、MOV、MKV、MP3、WAV、M4A 和 SRT。',
      nextStageWaiting: '等待中',
      recognitionToTranslation: '识别 -> 翻译',
      translationOnly: '翻译',
      loadingTranslationConfig: '正在读取已保存的翻译配置。',
      previewOutputModeHint: '这会影响后续导出的字幕格式。',
      exportPathHint: '导出成功后，这里会显示保存路径。',
    },
    routes: {
      recognitionToTranslation: '识别 -> 翻译',
      srtParseToTranslation: 'SRT 解析 -> 翻译',
      translationOnly: '翻译',
    },
    metrics: {
      preparedSegmentsHint: '已有字幕片段时，可以直接再次翻译而无需重新导入。',
      preparedSegmentsPending: '点击开始翻译后会自动准备字幕片段。',
      exportBilingualHint: '每条字幕会按“原文一行，译文一行”的格式写入。',
      exportSingleHint: '导出时会优先写入译文，若译文为空则回退到原文。',
    },
    notes: {
      translationNeedImport: '请先导入文件，LinguaSub 才能准备翻译流程。',
      translationRecognition:
        '点击开始翻译后会先进行本地识别，再把字幕片段发送给当前服务商。',
      translationSrt:
        '点击开始翻译后会先解析 SRT，再把字幕片段发送给当前服务商。',
      previewReady: '翻译结果已经写回共享项目状态，现在可以继续预览和编辑。',
      exportReady:
        '导出会直接使用当前项目里的字幕片段，包括预览页中的修改。文件名留空时会自动命名。',
      importNeedFile: '请先导入文件，LinguaSub 才能判断正确的处理路径。',
      srtImported: 'SRT 导入成功，现在可以进入翻译设置继续。',
      mediaImported: '媒体文件导入成功，现在可以进入翻译设置继续。',
      settingsReady: '这里可以查看当前配置，并在需要时启动 Windows 卸载。',
    },
    hints: {
      importDefault: '请先导入支持的文件，准备下一步流程。',
      translationDone: '翻译已完成。',
      exportWriting: '正在把当前字幕包写入磁盘。',
      exportReady: '选择导出模式和文件名后即可生成最终 SRT。',
      settingsReady: '设置页已就绪，可查看配置或启动卸载。',
    },
    errors: {
      importBeforeTranslation: '开始翻译前请先导入文件。',
      translationConfigMissing: '翻译设置还没有加载完成。',
      translationFlowFailed: '翻译流程失败，请重试。',
      missingSubtitleParsePath: '导入的字幕文件缺少 SRT 解析路径。',
      missingRecognitionPath: '导入的媒体文件缺少识别路径。',
      missingUpdatedSegment: '翻译服务没有返回更新后的字幕片段。',
      noSubtitleSegmentsToExport: '当前没有可导出的字幕片段。',
      noRecognitionTextToExport: '暂无识别内容可导出，请先完成视频识别。',
      exportFailed: '导出失败，请重试。',
      startupCheckFailed: '无法加载启动环境检查。',
      configLoadFailed: '无法加载翻译配置。',
      uninstallStartFailed: '无法启动 Windows 卸载流程。',
    },
  },
  importPage: {
    sections: {
      import: {
        eyebrow: '导入',
        title: '选择一个源文件',
        description: '拖入文件，或点击按钮从本机选择。',
      },
      summary: {
        eyebrow: '摘要',
        title: '已导入文件信息',
        description: '一旦后端识别了文件类型，LinguaSub 就会把结果写入当前项目状态。',
      },
      workflow: {
        eyebrow: '流程',
        title: '预计处理路径',
        description: '这个流程预览会明确显示文件是先进入识别，还是直接跳到翻译。',
      },
      backend: {
        eyebrow: '后端',
        title: '预留的交接载荷',
        description: '这份响应就是统一的导入契约，后面的 ASR 和 SRT 解析模块都基于它继续工作。',
      },
      environment: {
        eyebrow: '环境',
        title: '首次启动检查',
        description: 'Step 10 增加了启动环境报告，让开发版和发布版都能明确说明：哪些功能已可用，哪些还依赖本地环境，以及用户数据应该放在哪里。',
      },
    },
    supportedInputLabel: '支持的输入',
    pathTitle: '粘贴或输入本地文件路径',
    pathDescription: '支持完整路径或相对路径，例如',
    localPath: '本地路径',
    helperText: '也可以直接粘贴本机绝对路径。',
    emptySummaryTitle: '还没有选择文件',
    emptySummaryDescription: '选择视频、音频或 SRT 后，这里会显示文件信息和下一步。',
    workflowWaitingTitle: '正在等待导入文件',
    workflowWaitingDescription: '媒体文件会生成识别载荷，SRT 文件会生成字幕解析载荷。',
    noEnvironmentTitle: '正在等待环境报告',
    noEnvironmentDescription: 'LinguaSub 会从本地后端读取依赖和存储信息。',
    mediaTypes: {
      video: '视频',
      audio: '音频',
      subtitle: 'SRT 字幕',
    },
    formatGroups: [
      { title: '视频', items: ['MP4', 'MOV', 'MKV'] },
      { title: '音频', items: ['MP3', 'WAV', 'M4A'] },
      { title: '字幕', items: ['SRT'] },
    ],
    workflowExamples: [
      {
        title: '视频 / 音频路径',
        description: '媒体文件会先进入本地识别，然后再进入翻译和导出。',
        steps: ['视频或音频', '识别', '翻译', '导出'],
      },
      {
        title: 'SRT 路径',
        description: 'SRT 会跳过识别，直接进入翻译和导出。',
        steps: ['SRT', '翻译', '导出'],
      },
    ],
    environment: {
      mediaReady: '就绪',
      mediaMissing: '缺少本地依赖',
      srtReady: '就绪',
      srtBlocked: '受阻',
      backendReachable: '已连接',
      backendUnreachable: '未连接',
      apiKeyMissing: '未配置 API Key',
      startupWarnings: '启动提醒',
      startupSuccessTitle: '启动检查通过',
      startupSuccessDescription: '当前机器已经满足上面展示的工作流要求。',
      nextActions: '建议操作',
      dependencies: {
        backend: {
          label: 'LinguaSub 后端',
          requiredFor: '启动检查与本地流程编排',
          details: '只要这个环境报告能返回，就说明本地后端已经可达。',
          hint: '发布版会在应用启动时自动拉起后端 sidecar。',
        },
        ffmpeg: {
          label: 'FFmpeg',
          requiredFor: '视频与音频识别',
          details: 'LinguaSub 会先用 FFmpeg 从视频中抽取音频，再交给本地识别。',
          hint: '请在发布版资源目录中附带 ffmpeg.exe，安装后应用会自动查找它。',
        },
        fasterWhisperRuntime: {
          label: 'faster-whisper 运行时',
          requiredFor: '本地语音识别',
          details: '这里指的是 faster-whisper 运行依赖本身，不包含具体的 Whisper 模型文件。',
          hint: '发布版需要把 faster-whisper、ctranslate2、tokenizers 等运行时一起打进后端 sidecar。',
        },
      },
      models: {
        title: 'Whisper 模型文件',
        description: '模型文件不会打进安装包。首次使用时再下载到用户数据目录。',
        selectLabel: '识别模型大小',
        optionLabel: (label: string, status: string) => `${label} · ${status}`,
        modelLabel: (label: string) => `${label} 模型`,
        storageHint: (path: string) => `默认保存位置：${path}`,
        selectedStorageHint: (path: string) => `当前已记住的模型目录：${path}`,
        downloadStatusTitle: '模型下载状态',
        dialogTitle: '选择模型保存位置',
        dialogDescription:
          '下载前先确认 Whisper 模型要保存到哪里。你可以继续使用默认目录，也可以改到其他磁盘文件夹。',
        useDefaultStorage: '使用默认目录',
        useCustomStorage: '选择其他文件夹',
        customStorageDescription: '手动选择一个新的模型保存目录',
        customPathLabel: '自定义目录',
        customPathPlaceholder: '例如 D:\\LinguaSub\\speech-models',
        browseFolder: '选择文件夹',
        rememberStoragePath: '记住这次选择，后续下载继续使用该目录',
        cancel: '取消',
        confirmDownload: '开始下载',
        pickerFailed: '无法打开文件夹选择器，请手动输入目录。',
        customPathRequired: '请选择一个有效的模型保存目录后再开始下载。',
        downloadModelName: (modelName: string) => `当前模型：${modelName}`,
        targetPathLabel: (path: string) => `目标目录：${path}`,
        verifiedStorageHint: (path: string) => `LinguaSub 已校验模型文件完整，并已刷新当前目录状态：${path}`,
        downloadFailed: '模型下载或校验失败，请检查目录后重试。',
      },
      warnings: {
        apiKey: '当前默认翻译服务还没有 API Key，翻译请求会失败。',
        ffmpeg: 'FFmpeg 未就绪，视频和音频文件暂时无法进入本地识别流程。',
        fasterWhisperRuntime: 'faster-whisper 运行时未就绪，媒体转字幕功能暂时不可用。',
        speechModels: '运行时已经就绪，但还没有下载任何 Whisper 模型文件。',
      },
      actions: {
        apiKey: '请在翻译设置或后续设置页中补充默认服务商的 API Key。',
        ffmpeg: '确认安装包包含 bundled ffmpeg.exe，并让后端从应用 runtime 目录中查找它。',
        fasterWhisperRuntime: '重新打包后端 sidecar，并确保 faster-whisper 运行时依赖已经被收进 PyInstaller 产物。',
        speechModels: (path: string) => `在导入页下载 tiny / base / small 模型。默认目录：${path}`,
        configPath: '发布版建议把 LINGUASUB_CONFIG_PATH 指向用户数据目录，避免把配置写进安装目录。',
      },
      usingTranslationConfig: (provider: string, model: string) => `${provider} / ${model}`,
    },
    errors: {
      emptyPath: '请先输入本地文件路径。',
    },
  },
  translationPage: {
    sections: {
      translation: {
        eyebrow: '翻译',
        title: '选择翻译设置',
        description: 'Step 7 会把导入得到的字幕片段接入现有翻译服务。媒体先识别，SRT 先解析。',
      },
      source: {
        eyebrow: '来源',
        title: '当前翻译输入',
        description: '下面这些卡片会显示当前会先进入识别，还是直接进入翻译。',
      },
      progress: {
        eyebrow: '进度',
        title: '处理交接',
        description: '这条流程会显示 LinguaSub 如何把导入内容转成可翻译的字幕片段。',
      },
    },
    loadingConfigTitle: '正在加载配置',
    loadingConfigDescription: 'LinguaSub 正在从本地后端读取你保存的服务商设置。',
    configUnavailableTitle: '配置不可用',
    configUnavailableDescription: 'LinguaSub 还没有成功读取翻译配置，可以尝试重新加载。',
    readinessNeedImport: '请先导入文件，翻译设置才会解锁。',
    readinessPreparedSegments: (count: number) => `已准备 ${count} 条字幕片段。`,
    readinessRecognition: 'LinguaSub 会先进行本地识别，再把字幕片段发送到翻译服务。',
    readinessSrt: 'LinguaSub 会先解析 SRT，再把字幕片段直接发送到翻译服务。',
    routeWaiting: '等待导入',
    routeRecognition: '识别 -> 翻译',
    routeSrt: 'SRT 解析 -> 翻译',
    providerConfigured: '当前服务商可以立即用于翻译。',
    providerMissingApiKey: '请在后续设置中补充 API Key，否则翻译会返回错误。',
    openaiCompatibleProvider: 'OpenAI 兼容接口',
    deepseekProvider: 'DeepSeek 服务商',
    outputModeHint: '用于决定后续导出的字幕格式。',
    noImportedFileTitle: '还没有导入文件',
    noImportedFileDescription: '请先导入本地文件，这里会显示后续的识别或字幕解析交接。',
    progressImportDone: (fileName: string) => `已导入 ${fileName}。`,
    progressImportWaiting: '正在等待源文件。',
    progressSrtReady: 'SRT 片段已准备完成。',
    progressSrtPending: '开始翻译后会先执行 SRT 解析。',
    progressRecognitionReady: '识别结果已准备完成。',
    progressRecognitionPending: '开始翻译后会先执行本地 faster-whisper 识别。',
    progressTranslationDone: '翻译后的字幕文本已经可以进入预览。',
    progressTranslationPending: '当前字幕片段会按批次发送给已配置的翻译服务商。',
  },
  previewPage: {
    sections: {
      preview: {
        eyebrow: '预览',
        title: '翻译后的字幕结果',
        description: 'Step 7 会把译文写回每条 SubtitleSegment，然后把项目推进到预览阶段。',
      },
      segments: {
        eyebrow: '片段',
        title: '可编辑的字幕列表',
        description: '可以搜索、编辑、保存，也可以单独重翻某一条字幕，同时保持共享项目状态同步更新。',
      },
    },
    nothingToPreviewDescription: '请先执行翻译，LinguaSub 才会在这里展示译后的字幕片段。',
    noMatchesDescription: '试试别的关键词。搜索会实时检查原文和译文。',
    noSegmentsDescription: '翻译完成后，LinguaSub 会在这里列出可编辑的字幕行。',
    retranslationFailed: '重翻失败',
    searchLabel: '搜索字幕',
    showingLabel: '当前显示',
    lastSaved: (time: string) => `上次保存于 ${time}`,
  },
  exportPage: {
    sections: {
      export: {
        eyebrow: '导出',
        title: '选择字幕输出',
        description: 'Step 9 会读取当前 ProjectState.segments，包括预览页里的修改，并把最终 SRT 写入磁盘。',
      },
      summary: {
        eyebrow: '摘要',
        title: '当前字幕包',
        description: '这里的数据直接来自共享项目状态，所以预览里的修改会立即反映到导出结果中。',
      },
    },
    currentProjectFolder: '当前项目目录',
    destinationDescription: '默认会把导出的字幕保存到导入源文件所在目录。',
    resolvedFileNameDescription: '文件名留空时，会使用系统自动生成的默认名称。',
    bilingualDescription: '每条字幕会按“原文一行，译文一行”的格式导出。',
    singleDescription: '导出时会优先使用译文，如果译文为空就回退到原文。',
    writingDescription: '后端正在生成 SRT 内容并把文件保存到磁盘。',
    readyDescription: '使用下面的主按钮即可写出字幕文件。',
    noSubtitleDescription: '请先完成翻译或解析字幕片段，导出在没有字幕数据时会保持禁用。',
    missingLinesDescription: (count: number) => `${count} 条字幕的译文还是空的。双语导出要求每一条字幕都有译文，否则后端会返回清晰报错。`,
    invalidTimelineDescription: (count: number) => `${count} 条字幕存在无效时间范围。只有当所有字幕的结束时间都晚于开始时间时，导出才会成功。`,
    lastExportDescription: (fileName: string) => `${fileName} 已成功写入。`,
    noProjectDescription: '请先导入并处理文件，这里才会显示当前字幕包。',
  },
  settingsPage: {
    sections: {
      settings: {
        eyebrow: '设置',
        title: '当前应用设置',
        description: '这里汇总当前界面语言、默认翻译服务和输出模式，方便在卸载前再次确认。',
      },
      uninstall: {
        eyebrow: '卸载',
        title: '从 Windows 卸载 LinguaSub',
        description: '确认后会调用 NSIS 卸载程序。LinguaSub 会先退出，再由 Windows 继续卸载。',
      },
    },
    labels: {
      interfaceLanguage: '界面语言',
    },
    languageHint: '右上角语言切换会立即生效，并保留到下次启动。',
    uninstallAvailability: 'Windows 卸载可用',
    uninstallWarningTitle: '卸载前请确认',
    uninstallWarningDescription: '卸载会关闭当前应用，并交给 Windows 卸载程序继续处理。',
    uninstallStatusTitle: '卸载流程',
    uninstallHelper: '建议先保存当前字幕和导出结果，然后再继续卸载。',
    uninstallErrorTitle: '卸载启动失败',
    uninstallCloseReminder: '确认后 LinguaSub 会自动退出。',
    uninstallingHint: 'LinguaSub 正在退出，并准备启动 Windows 卸载程序。',
    uninstallConfirm:
      '确定要卸载 LinguaSub 吗？\n\n确认后会关闭当前应用，并启动 Windows 卸载程序。',
  },
} as const

const enMessages = {
  common: {
    appName: 'LinguaSub',
    currentStage: 'Current stage',
    taskStatus: 'Task Status',
    language: {
      label: 'UI Language',
      zh: '中文',
      en: 'English',
    },
    buttons: {
      previousStep: 'Previous Step',
      importToContinue: 'Import to Continue',
      openTranslationSetup: 'Open Translation Setup',
      startTranslation: 'Start Translation',
      working: 'Working...',
      openExport: 'Open Export',
      exporting: 'Exporting...',
      exportSrt: 'Export SRT',
      exportWord: 'Export Word',
      reloadConfig: 'Reload Config',
      translateAgain: 'Translate Again',
      useAutoName: 'Use Auto Name',
      saveChanges: 'Save Changes',
      retranslate: 'Retranslate',
      retranslating: 'Retranslating...',
      reloadStartupCheck: 'Reload Startup Check',
      importFile: 'Import File',
      inspecting: 'Inspecting...',
      uninstallLinguaSub: 'Uninstall LinguaSub',
      uninstalling: 'Starting Uninstall...',
      downloadModel: 'Download Model',
      downloadingModel: 'Downloading Model...',
    },
    outputModes: {
      bilingual: 'Bilingual',
      single: 'Single language',
    },
    statuses: {
      idle: 'idle',
      transcribing: 'transcribing',
      translating: 'translating',
      exporting: 'exporting',
      done: 'done',
      error: 'error',
    },
    runtimeModes: {
      development: 'Development',
      release: 'Release',
    },
    availability: {
      ready: 'Ready',
      missing: 'Missing',
      blocked: 'Blocked',
      needsDependencies: 'Needs local dependencies',
      available: 'Available',
      downloading: 'Downloading',
      unavailable: 'Unavailable',
      error: 'Error',
    },
    providers: {
      openaiCompatible: 'OpenAI Compatible',
      deepseek: 'DeepSeek',
    },
    exportFormats: {
      srt: 'SRT',
      word: 'Word',
      recognition_text: 'Recognition Text TXT',
    },
    transcriptionProviders: {
      openaiSpeech: 'Cloud transcription (Recommended)',
      localFasterWhisper: 'Local transcription (Advanced / Offline)',
    },
    wordExportModes: {
      bilingualTable: 'Bilingual table',
      transcript: 'Transcript',
    },
    asrLanguages: {
      auto: 'Auto detect',
      zh: 'Chinese',
      en: 'English',
      ja: 'Japanese',
      ko: 'Korean',
    },
    asrQualityPresets: {
      speed: 'Speed',
      balanced: 'Balanced',
      accuracy: 'Accuracy',
    },
    workflowSteps: {
      Video: 'Video',
      Audio: 'Audio',
      SRT: 'SRT',
      Recognition: 'Recognition',
      Translation: 'Translation',
      Export: 'Export',
    },
    summary: {
      file: 'File',
      path: 'Path',
      route: 'Route',
      status: 'Status',
      sourceFile: 'Source file',
      currentFile: 'Current file',
      projectStatus: 'Project status',
      outputMode: 'Output mode',
      translatedSegments: 'Translated segments',
      translatedRows: 'Translated rows',
      subtitleRows: 'Subtitle rows',
      livePreviewEdits: 'Live preview edits',
      filteredRows: 'Filtered rows',
      lastRun: 'Last run',
      nextStage: 'Next stage',
      type: 'Type',
      name: 'Name',
      translatedCount: 'Translated count',
      mode: 'Mode',
      backend: 'Backend',
      configPath: 'Config path',
      recommendedUserData: 'Recommended user data',
      speechModelFolder: 'Speech model folder',
      mediaWorkflow: 'Media workflow',
      srtWorkflow: 'SRT workflow',
      selectedAsrModel: 'Recognition model',
      translationConfig: 'Translation config',
      destinationFolder: 'Destination folder',
      resolvedFileName: 'Resolved file name',
      exportFormat: 'Export format',
      exportStatus: 'Export status',
      subtitlePackage: 'Subtitle package',
      lastExport: 'Last export',
    },
    placeholders: {
      searchSubtitle: 'Search source or translation',
      importPath: 'D:\\media\\demo.srt',
      model: 'gpt-4.1-mini',
    },
    misc: {
      loading: 'Loading...',
      loadingConfig: 'Loading config',
      notRecorded: 'Not recorded',
      notSelected: 'Not selected',
      waiting: 'Waiting',
      notExported: 'Not exported',
      readyToExportAgain: 'Ready to export again',
      writingFile: 'Writing file...',
      notExportedYet: 'Not exported yet',
      configured: 'Configured',
      missing: 'Missing',
      includedInExport: 'Included in export',
      alreadySaved: 'Already saved',
      noSaveRecordedYet: 'No save recorded yet',
      noProjectLoaded: 'No project loaded',
      noImportedFile: 'No imported file yet',
      nothingToPreview: 'Nothing to preview yet',
      noSegmentsAvailable: 'No subtitle segments available',
      noMatchesFound: 'No matches found',
      configUnavailable: 'Config unavailable',
      waitingForEnvironmentReport: 'Waiting for environment report',
      startupCheckPassed: 'Startup check passed',
      startupCheckFailed: 'Startup check failed',
      importFailed: 'Import failed',
      exportFailed: 'Export failed',
      translationFlowFailed: 'Translation flow failed',
      configError: 'Config error',
      noSubtitleContent: 'No subtitle content',
      missingTranslatedLines: 'Missing translated lines',
      timelineNeedsAttention: 'Timeline needs attention',
      lastExportCompleted: 'Last export completed',
      searchSubtitles: 'Search subtitles',
      showing: 'Showing',
      editState: 'Edit state',
      unsavedChanges: 'Unsaved changes',
      saved: 'Saved',
      sourceText: 'Source text',
      translatedText: 'Translated text',
      provider: 'Provider',
      model: 'Model',
      baseUrl: 'Base URL',
      apiKey: 'API key',
      currentRoute: 'Current route',
      preparedSegments: 'Prepared segments',
      supportedInput: 'Supported input',
      import: 'Import',
      source: 'Source',
      progress: 'Progress',
      preview: 'Preview',
      segments: 'Segments',
      export: 'Export',
      summary: 'Summary',
      workflow: 'Workflow',
      backend: 'Backend',
      environment: 'Environment',
      translation: 'Translation',
      unknown: 'Unknown',
      srtSubtitle: 'SRT Subtitle',
      video: 'Video',
      audio: 'Audio',
    },
  },
  sidebar: {
    eyebrow: 'Windows Desktop Workflow',
    description: 'Subtitle generation and export tool',
    items: {
      import: {
        label: 'Import',
        description: 'Choose a video, audio, or subtitle file',
      },
      recognition: {
        label: 'ASR',
        description: 'Prepare faster-whisper settings',
      },
      translation: {
        label: 'Translate',
        description: 'Choose provider, model, and output mode',
      },
      preview: {
        label: 'Preview',
        description: 'Review source and translated lines',
      },
      export: {
        label: 'Export',
        description: 'Generate SRT output',
      },
      settings: {
        label: 'Settings',
        description: 'Manage providers and defaults',
      },
    },
    ariaLabel: 'Primary workflow',
  },
  stepHeader: {
    step: (current: number, total: number) => `Step ${current}/${total}`,
  },
  app: {
    workspace: {
      import: {
        title: 'Import Source',
        description:
          'Start with a local video, audio, or SRT file. LinguaSub detects the file type automatically and prepares the right workflow.',
      },
      translation: {
        title: 'Translation Setup',
        description:
          'Choose the translation provider, model, and output mode. LinguaSub prepares subtitle segments from recognition or SRT parsing before sending them to translation.',
      },
      preview: {
        title: 'Subtitle Preview',
        description:
          'Review the translated result. Every subtitle segment in the shared project state now carries both source text and translated text.',
      },
      export: {
        title: 'Export Results',
        description:
          'Choose an export type, confirm a few options, and generate the final file.',
      },
      settings: {
        title: 'App Settings',
        description:
          'Review the current UI language and translation configuration, then start the Windows uninstall flow from here when needed.',
      },
    },
    labels: {
      supportedInputHint: 'MP4, MOV, MKV, MP3, WAV, M4A, and SRT are supported.',
      nextStageWaiting: 'Waiting',
      recognitionToTranslation: 'Recognition -> Translation',
      translationOnly: 'Translation',
      loadingTranslationConfig: 'Loading saved translation config.',
      previewOutputModeHint: 'This controls how the subtitle result will be formatted during export.',
      exportPathHint: 'The saved export path will appear here after a successful export.',
    },
    routes: {
      recognitionToTranslation: 'Recognition -> Translation',
      srtParseToTranslation: 'SRT Parse -> Translation',
      translationOnly: 'Translation',
    },
    metrics: {
      preparedSegmentsHint:
        'Existing subtitle segments can be translated again without re-importing.',
      preparedSegmentsPending:
        'Subtitle segments will be prepared automatically when translation starts.',
      exportBilingualHint:
        'Each subtitle block will use one source line and one translated line.',
      exportSingleHint:
        'Export writes translated text first and falls back to source text when needed.',
    },
    notes: {
      translationNeedImport: 'Import a file first so LinguaSub can prepare the translation flow.',
      translationRecognition:
        'Starting translation runs local recognition first, then sends subtitle segments to the selected provider.',
      translationSrt:
        'Starting translation parses the SRT first, then sends subtitle segments to the selected provider.',
      previewReady:
        'Translation results are now stored in the shared project state and ready for preview and editing.',
      exportReady:
        'Export uses the current project segments, including preview edits. Leave the file name empty to auto-name the SRT.',
      importNeedFile: 'Import a file first so LinguaSub can determine the correct route.',
      srtImported: 'SRT imported successfully. Open translation setup to continue.',
      mediaImported: 'Media imported successfully. Open translation setup to continue.',
      settingsReady:
        'Review the current configuration here and launch the Windows uninstall flow when needed.',
    },
    hints: {
      importDefault: 'Import a supported file to prepare the next module.',
      translationDone: 'Translation completed successfully.',
      exportWriting: 'Writing the current subtitle package to disk.',
      exportReady: 'Choose export mode and file name to generate the final SRT.',
      settingsReady: 'Settings are ready. Review the config or start the uninstall flow.',
    },
    errors: {
      importBeforeTranslation: 'Import a file before starting translation.',
      translationConfigMissing: 'Translation settings are not loaded yet.',
      translationApiSetupRequired:
        'The default translation provider is not configured yet. Open Settings and save provider, base URL, API key, and model first.',
      translationFlowFailed: 'Translation flow failed. Please try again.',
      missingSubtitleParsePath: 'The imported subtitle file is missing the SRT parse path.',
      missingRecognitionPath: 'The imported media file is missing the recognition path.',
      missingUpdatedSegment:
        'The translation service did not return an updated subtitle segment.',
      noSubtitleSegmentsToExport: 'There are no subtitle segments to export.',
      noRecognitionTextToExport:
        'No recognition text available. Please transcribe a video first.',
      exportFailed: 'Export failed. Please try again.',
      startupCheckFailed: 'Could not load the startup environment check.',
      configLoadFailed: 'Could not load the translation config.',
      uninstallStartFailed: 'Could not start the Windows uninstall flow.',
    },
  },
  importPage: {
    sections: {
      import: {
        eyebrow: 'Import',
        title: 'Choose a source file',
        description: 'Drop a file here, or choose one from this computer.',
      },
      summary: {
        eyebrow: 'Summary',
        title: 'Imported file details',
        description: 'Once the backend recognizes the file type, LinguaSub stores the result in the current project state.',
      },
      workflow: {
        eyebrow: 'Workflow',
        title: 'Expected processing route',
        description: 'The flow preview makes it clear whether the file will go through recognition or jump directly to translation.',
      },
      backend: {
        eyebrow: 'Backend',
        title: 'Reserved handoff payload',
        description: 'This response is the single import contract that later ASR and SRT parsing modules can build on.',
      },
      environment: {
        eyebrow: 'Environment',
        title: 'First start check',
        description: 'Step 10 adds a startup report so development builds and packaged builds can explain what is ready, what still depends on local setup, and where user data should live.',
      },
    },
    supportedInputLabel: 'Supported input',
    pathTitle: 'Paste or type a local file path',
    pathDescription: 'Use a full or relative path such as',
    localPath: 'Local path',
    helperText: 'You can also paste a local absolute path.',
    emptySummaryTitle: 'No file selected yet',
    emptySummaryDescription: 'Choose a video, audio, or SRT file to see file details and the next step.',
    workflowWaitingTitle: 'Waiting for an imported file',
    workflowWaitingDescription: 'Media files will produce a recognition payload. SRT files will produce a subtitle parsing payload.',
    noEnvironmentTitle: 'Waiting for environment report',
    noEnvironmentDescription: 'LinguaSub will load dependency and storage information from the local backend.',
    mediaTypes: {
      video: 'Video',
      audio: 'Audio',
      subtitle: 'SRT Subtitle',
    },
    formatGroups: [
      { title: 'Video', items: ['MP4', 'MOV', 'MKV'] },
      { title: 'Audio', items: ['MP3', 'WAV', 'M4A'] },
      { title: 'Subtitle', items: ['SRT'] },
    ],
    workflowExamples: [
      {
        title: 'Video / Audio route',
        description: 'Media files enter local recognition first, then continue to translation and export.',
        steps: ['Video or Audio', 'Recognition', 'Translation', 'Export'],
      },
      {
        title: 'SRT route',
        description: 'SRT files skip recognition and move directly to translation and export.',
        steps: ['SRT', 'Translation', 'Export'],
      },
    ],
    environment: {
      mediaReady: 'Ready',
      mediaMissing: 'Needs local dependencies',
      srtReady: 'Ready',
      srtBlocked: 'Blocked',
      backendReachable: 'Reachable',
      backendUnreachable: 'Unavailable',
      apiKeyMissing: 'API key not configured',
      startupWarnings: 'Startup warnings',
      startupSuccessTitle: 'Startup check passed',
      startupSuccessDescription: 'The current machine is ready for the workflows shown above.',
      nextActions: 'Next actions',
      dependencies: {
        backend: {
          label: 'LinguaSub backend',
          requiredFor: 'Startup checks and local workflow orchestration',
          details: 'If this environment report is visible, the local backend sidecar is already reachable.',
          hint: 'The packaged app should start the backend sidecar automatically on launch.',
        },
        ffmpeg: {
          label: 'FFmpeg',
          requiredFor: 'Video and audio recognition',
          details: 'LinguaSub uses FFmpeg to extract audio from video files before local transcription.',
          hint: 'Bundle ffmpeg.exe inside the release runtime folder so the installed app can find it automatically.',
        },
        fasterWhisperRuntime: {
          label: 'faster-whisper runtime',
          requiredFor: 'Local speech recognition',
          details: 'This is the faster-whisper runtime itself, separate from the Whisper model files.',
          hint: 'Package faster-whisper, ctranslate2, tokenizers, and related runtime libraries inside the backend sidecar.',
        },
      },
      models: {
        title: 'Whisper model files',
        description: 'Model files stay out of the installer and are downloaded into user data on first use.',
        selectLabel: 'Recognition model size',
        languageLabel: 'Recognition language',
        languageHint:
          'If you already know the source language, choose it here to reduce wrong-language recognition.',
        qualityLabel: 'Recognition quality',
        qualityDescriptions: {
          speed:
            'Fastest result for clean audio previews. Uses lighter decoding and less subtitle cleanup.',
          balanced:
            'Recommended default. Uses stronger decoding plus subtitle readability cleanup without being too slow.',
          accuracy:
            'Best for difficult audio. Uses stronger decoding and stricter subtitle segmentation, but runs slower on CPU.',
        },
        optionLabel: (label: string, status: string) => `${label} · ${status}`,
        modelLabel: (label: string) => `${label} model`,
        storageHint: (path: string) => `Default storage location: ${path}`,
        selectedStorageHint: (path: string) => `Saved model storage location: ${path}`,
        downloadStatusTitle: 'Model download status',
        dialogTitle: 'Choose where the model is stored',
        dialogDescription:
          'Confirm the Whisper model storage folder before download starts. You can keep the default folder or select another drive and directory.',
        useDefaultStorage: 'Use default folder',
        useCustomStorage: 'Choose another folder',
        customStorageDescription:
          'Pick a parent folder. LinguaSub stores models inside a managed LinguaSub\\Models subfolder there.',
        customPathLabel: 'Custom folder',
        customPathPlaceholder: 'For example D:\\AIAssets',
        browseFolder: 'Browse Folder',
        rememberStoragePath: 'Remember this storage location for future model downloads',
        cancel: 'Cancel',
        confirmDownload: 'Start Download',
        pickerFailed: 'Could not open the folder picker. Enter a folder path manually.',
        customPathRequired:
          'Choose a valid model storage folder before starting the download.',
        downloadModelName: (modelName: string) => `Model: ${modelName}`,
        targetPathLabel: (path: string) => `Target folder: ${path}`,
        verifiedStorageHint: (path: string) => `LinguaSub verified the downloaded model files and refreshed the folder status: ${path}`,
        downloadFailed:
          'Model download verification failed. Please check the folder and retry.',
      },
      warnings: {
        apiKey: 'The active translation provider does not have an API key yet. Translation requests will fail until one is configured.',
        ffmpeg: 'FFmpeg is missing. Video and audio files cannot enter the local recognition route yet.',
        fasterWhisperRuntime: 'The faster-whisper runtime is missing. Media transcription is unavailable until the runtime is bundled.',
        speechModels: 'The runtime is ready, but no Whisper model files have been downloaded yet.',
      },
      actions: {
        apiKey: 'Open Translation Setup and save the API key for the default provider.',
        ffmpeg: 'Make sure the packaged app bundles ffmpeg.exe inside its runtime resources.',
        fasterWhisperRuntime: 'Rebuild the backend sidecar and collect the faster-whisper runtime dependencies into the PyInstaller output.',
        speechModels: (path: string) => `Download tiny / base / small from the Import page. Default folder: ${path}`,
        configPath: 'For release builds, point LINGUASUB_CONFIG_PATH to the user data directory instead of the install folder.',
      },
      usingTranslationConfig: (provider: string, model: string) => `${provider} / ${model}`,
    },
    errors: {
      emptyPath: 'Enter a local file path first.',
    },
  },
  translationPage: {
    sections: {
      translation: {
        eyebrow: 'Translation',
        title: 'Choose the translation settings',
        description: 'Step 7 connects imported subtitle segments to the existing translation service. Media files transcribe first. SRT files parse first.',
      },
      source: {
        eyebrow: 'Source',
        title: 'Current translation input',
        description: 'The cards below show what will be sent into recognition or straight into translation.',
      },
      progress: {
        eyebrow: 'Progress',
        title: 'Processing handoff',
        description: 'This sequence shows how LinguaSub turns imported input into translated subtitle segments.',
      },
    },
    loadingConfigTitle: 'Loading config',
    loadingConfigDescription: 'LinguaSub is reading your saved provider settings from the local backend.',
    configUnavailableTitle: 'Config unavailable',
    configUnavailableDescription: 'LinguaSub could not load the translation config yet. Use reload to try again.',
    readinessNeedImport: 'Import a file first to unlock translation settings.',
    readinessPreparedSegments: (count: number) => `Prepared ${count} subtitle segment${count > 1 ? 's' : ''}.`,
    readinessRecognition: 'LinguaSub will run local recognition before sending subtitle segments to translation.',
    readinessSrt: 'LinguaSub will parse the SRT file and send the segments directly to translation.',
    routeWaiting: 'Waiting for import',
    routeRecognition: 'Recognition -> Translation',
    routeSrt: 'SRT Parse -> Translation',
    providerConfigured: 'This provider can be used immediately for translation.',
    providerMissingApiKey: 'Add the API key in a later settings step, or translation will return an error.',
    apiConfigNeededTitle: 'Translation API setup is still required',
    apiConfigNeededDescription:
      'Before starting translation, open Settings and save provider, base URL, API key, and model.',
    openSettingsAction: 'Open Settings',
    openaiCompatibleProvider: 'OpenAI-compatible provider',
    deepseekProvider: 'DeepSeek provider',
    outputModeHint: 'This controls how export will format the subtitle result later.',
    noImportedFileTitle: 'No imported file yet',
    noImportedFileDescription: 'Import a local file first. This panel will then show the recognition or subtitle parsing handoff.',
    progressImportDone: (fileName: string) => `Imported ${fileName}.`,
    progressImportWaiting: 'Waiting for a source file.',
    progressSrtReady: 'SRT segments are ready.',
    progressSrtPending: 'SRT parsing will happen before translation starts.',
    progressRecognitionReady: 'Recognition output is ready.',
    progressRecognitionPending: 'Local faster-whisper recognition will happen before translation starts.',
    progressTranslationDone: 'Translated subtitle text is ready for preview.',
    progressTranslationPending: 'The current subtitle segments will be sent to the configured translation provider in batches.',
    recognitionSummaryTitle: 'Recognition quality summary',
    recognitionSummarySettings: (
      modelSize: string,
      qualityPreset: string,
      language: string,
    ) => `Current recognition plan: ${modelSize} model · ${qualityPreset} preset · ${language}.`,
    rawQualitySummary: (
      modelSize: string,
      qualityPreset: string,
      requestedLanguage: string,
      detectedLanguage: string,
    ) =>
      `Raw transcription quality uses the ${modelSize} model, ${qualityPreset} preset, and ${requestedLanguage} input hint. Detected language: ${detectedLanguage}.`,
    readabilitySummary: (rawCount: number, finalCount: number) =>
      `Subtitle readability cleanup reshaped ${rawCount} raw segment${rawCount > 1 ? 's' : ''} into ${finalCount} subtitle row${finalCount > 1 ? 's' : ''}.`,
    translationBoundaryNote:
      'Translation quality is separate. If source subtitles already look wrong here, fix recognition settings before judging translation.',
    rawQualityPending:
      'Raw transcription quality will depend on the selected model, quality preset, and language hint once recognition starts.',
    readabilityPending:
      'Subtitle readability cleanup will split long lines and merge fragmented lines after raw recognition returns.',
  },
  previewPage: {
    sections: {
      preview: {
        eyebrow: 'Preview',
        title: 'Translated subtitle result',
        description: 'Step 7 writes translated text back into each SubtitleSegment, then moves the project into the preview stage.',
      },
      segments: {
        eyebrow: 'Segments',
        title: 'Editable subtitle list',
        description: 'Search, edit, save, and retranslate individual rows while keeping the shared project state in sync.',
      },
    },
    nothingToPreviewDescription: 'Run translation first. LinguaSub will then display the translated subtitle segments here.',
    noMatchesDescription: 'Try another keyword. Search checks both source text and translated text in real time.',
    noSegmentsDescription: 'After translation completes, LinguaSub will list editable subtitle rows here.',
    retranslationFailed: 'Retranslation failed',
    searchLabel: 'Search subtitles',
    showingLabel: 'Showing',
    lastSaved: (time: string) => `Last saved ${time}`,
    agent: {
      eyebrow: 'Agent',
      title: 'Subtitle Agent',
      description:
        'Generate quality diagnostics and content summaries from the current subtitles. The original subtitles will not be modified.',
      emptyTitle: 'No subtitle segments available',
      emptyDescription:
        'No subtitle segments available. Please transcribe or import subtitles first.',
      configError: 'Please configure a translation model API in Settings first.',
      qualityError: 'Subtitle quality analysis failed. Please try again.',
      summaryError: 'Content summary generation failed. Please try again.',
      actions: {
        analyzeQuality: 'Analyze Subtitle Quality',
        analyzingQuality: 'Analyzing...',
        generateSummary: 'Generate Content Summary',
        generatingSummary: 'Generating...',
      },
      qualityTitle: 'Quality diagnostics',
      qualityDescription: 'Review possible translation, timing, length, and format issues.',
      scoreLabel: 'score',
      issuesTitle: 'Issues',
      noIssues: 'No obvious issues found.',
      summaryTitle: 'Content summary',
      summaryDescription: 'Create a learning-oriented summary from the subtitle text.',
      oneSentenceTitle: 'One-sentence summary',
      chaptersTitle: 'Chapters',
      keywordsTitle: 'Keywords',
      studyNotesTitle: 'Study notes',
      noChapters: 'No chapters returned.',
      noKeywords: 'No keywords returned.',
      severities: {
        info: 'Info',
        warning: 'Warning',
        error: 'Error',
      },
      issueTypes: {
        empty_translation: 'Empty translation',
        missing_translation: 'Missing translation',
        timing_error: 'Timing error',
        too_long: 'Too long',
        bilingual_format_error: 'Bilingual format error',
        terminology_inconsistent: 'Terminology inconsistent',
        unnatural_translation: 'Unnatural translation',
      },
    },
  },
  exportPage: {
    sections: {
      export: {
        eyebrow: 'Export',
        title: 'Export results',
        description:
          'Choose an export type, confirm a few options, and generate the final file.',
      },
      summary: {
        eyebrow: 'Summary',
        title: 'Current subtitle package',
        description: 'These values come directly from the shared project state, so preview edits are included immediately in the export result.',
      },
    },
    currentProjectFolder: 'Current project folder',
    task: {
      targetLabel: 'Export type',
      targets: {
        subtitle: {
          title: 'Subtitle file',
          description: 'Generate an SRT subtitle file from the current segments.',
        },
        recognitionText: {
          title: 'Recognition Text TXT',
          description:
            'Export the original transcribed text for manual ASR accuracy review.',
        },
        word: {
          title: 'Word document',
          description: 'Generate a DOCX file for review, reading, or archiving.',
        },
        video: {
          title: 'Subtitled video',
          description: 'Burn subtitles into the original video and save a new MP4.',
        },
      },
      fileNameLabel: 'File name',
      fileNameHint: 'Leave empty to use the default name.',
      videoStyleTitle: 'Video style',
      videoStyleDescription: 'Automatically adapts to portrait / landscape video.',
      videoSourceLabel: 'Original video',
      noOriginalVideo:
        'No original video path is available. Generate subtitles from Video subtitle first.',
      noSegments: 'There are no subtitles yet. Finish recognition or translation first.',
      successTitle: 'Export complete',
      failureTitle: 'Export failed',
      failureHint: 'Check the path, permissions, or settings, then try again.',
      outputPathLabel: 'Saved to:',
      openFolder: 'Open folder',
      detailsTitle: 'View export details',
      projectSummaryTitle: 'Project summary',
      formatDetailsTitle: 'Format notes',
      outputRulesTitle: 'Output rules',
      videoNotesTitle: 'Video export',
      outputRulesDescription:
        'Subtitle and Word exports use the imported source folder by default. Video export asks for a full MP4 save path.',
      videoNotesDescription:
        'Video export uses the current full ProjectState.segments and lets the backend choose an adaptive ASS style.',
      buttons: {
        exportSubtitle: 'Export subtitle file',
        exportRecognitionText: 'Export Recognition Text TXT',
        exportWord: 'Export Word document',
        exportVideo: 'Export subtitled video',
        exporting: 'Exporting...',
        exportingVideo: 'Generating subtitled video...',
      },
    },
    formatLabel: 'Export format',
    wordModeLabel: 'Word mode',
    destinationDescription: 'LinguaSub saves the exported subtitle beside the imported source file by default.',
    resolvedFileNameDescription: 'Leave the file name empty to use the default auto-generated export name.',
    fileFormatValues: {
      srt: 'SRT (.srt)',
      word: 'Word (.docx)',
      recognition_text: 'Recognition Text TXT (.txt)',
    },
    fileFormatDescriptions: {
      srt:
        'SRT export keeps the subtitle timing structure and writes either bilingual or single-language subtitle blocks.',
      word:
        'Word export writes a real .docx document. Choose either a bilingual review table or a readable transcript layout.',
      recognition_text:
        'TXT export writes only the original recognition text with timestamps for ASR review.',
    },
    bilingualDescription: 'Source text and translated text will be written on separate lines.',
    singleDescription: 'Translated text is used first. If it is empty, LinguaSub falls back to the source text.',
    wordModeDescriptions: {
      bilingualTable:
        'The bilingual table writes one subtitle segment per row with start time, end time, source text, and translated text.',
      transcript:
        'The transcript layout writes each subtitle segment as a readable timestamped section with source text and translated text.',
    },
    writingDescription: 'The backend is generating the selected export file and saving it to disk.',
    readyDescription: (exportFormatLabel: string) =>
      `Use the primary action button below to write the ${exportFormatLabel} file.`,
    noSubtitleDescription: 'Translate or parse subtitle segments first. Export stays disabled until the project has subtitle rows.',
    missingLinesDescription: (count: number) => `${count} subtitle segment${count > 1 ? 's still have' : ' still has'} empty translated text. Bilingual export requires every row to have a translation.`,
    wordMissingTranslationsDescription: (count: number) =>
      `${count} subtitle segment${count > 1 ? 's have' : ' has'} empty translated text. Word export will keep those translation cells blank.`,
    invalidTimelineDescription: (count: number) => `${count} subtitle segment${count > 1 ? 's have' : ' has'} an invalid time range. Export will fail until every end time is after its start time.`,
    wordInvalidTimelineDescription: (count: number) =>
      `${count} subtitle segment${count > 1 ? 's have' : ' has'} missing or invalid timestamps. Word export will keep the row and show safe timestamp placeholders when needed.`,
    lastExportDescription: (fileName: string) => `${fileName} was written successfully.`,
    extensionTitle: 'Output file extension',
    extensionDescriptions: {
      srt:
        'SRT export always writes a .srt file. Both bilingual and single-language modes use the same SRT container.',
      wordBilingualTable:
        'Word export writes a .docx file containing a bilingual review table with one subtitle segment per row.',
      wordTranscript:
        'Word export writes a .docx file containing a readable transcript with timestamps, source text, and translated text.',
    },
    noProjectDescription: 'Import and process a file first. The export summary will then show the current subtitle package here.',
  },
  settingsPage: {
    sections: {
      settings: {
        eyebrow: 'Settings',
        title: 'API configuration and app settings',
        description:
          'Enter the provider, base URL, API key, and model here so translation is actually usable. Saving refreshes the current availability state immediately.',
      },
      verification: {
        eyebrow: 'Verification',
        title: 'Recommended verification route',
        description:
          'Use the shortest path to confirm translation works before depending on local transcription.',
      },
      uninstall: {
        eyebrow: 'Uninstall',
        title: 'Remove LinguaSub from Windows',
        description:
          'After confirmation, LinguaSub starts the NSIS uninstaller. The app closes first and Windows continues the uninstall flow.',
      },
    },
    labels: {
      interfaceLanguage: 'Interface language',
      apiStatus: 'API configuration status',
      activeProvider: 'Current default provider',
    },
    languageHint:
      'The language switch in the header applies immediately and stays active on the next launch.',
    apiAvailable: 'Ready for translation',
    apiMissing: 'Still missing',
    apiAvailableDescription:
      'The current default provider now has enough saved configuration to validate and start translation.',
    apiMissingDescription:
      'Translation is expected to fail until provider, base URL, API key, and model are saved.',
    activeProviderDescription:
      'This saved default provider is reused directly by the translation page.',
    baseUrlHelper:
      'Enter the provider chat completions base URL, such as an OpenAI-compatible or DeepSeek /v1 endpoint.',
    apiKeyPlaceholder: 'Enter your API key',
    apiKeyHelper:
      'The API key is stored in the local JSON config. Save first, then use Validate Config to test the connection.',
    outputModeDescription:
      'This becomes the default export mode on the next translation and export run.',
    saveAction: 'Save Config',
    saving: 'Saving...',
    validateAction: 'Validate Config',
    validating: 'Validating...',
    saveSuccessTitle: 'Config saved',
    saveSuccess:
      'The translation settings were written to the local config and the availability state has been refreshed.',
    saveFailed: 'Could not save the configuration. Please try again.',
    validationSuccessTitle: 'Connection works',
    validationFailed:
      'Validation failed. Check the provider, base URL, API key, and model, then try again.',
    apiConfigErrorTitle: 'API configuration needs attention',
    nextVerificationTitle: 'Recommended next step',
    nextVerificationDescription:
      'Import an SRT file next to verify translation with the shortest path. That route skips local transcription and checks the API flow directly.',
    goToImportAction: 'Import an SRT',
    bestVerificationTitle: 'Best way to verify translation',
    bestVerificationDescription:
      'Import an existing SRT file first. That route skips FFmpeg, faster-whisper, and local model dependencies so you can verify the translation API itself.',
    verificationSteps: [
      {
        label: 'Save API config',
        description: 'Fill in provider, base URL, API key, and model here, then click Save Config.',
      },
      {
        label: 'Import an SRT',
        description: 'Use the SRT route so translation can be verified without local transcription.',
      },
      {
        label: 'Start translation',
        description: 'Open Translation and check that translatedText is returned successfully.',
      },
      {
        label: 'Review preview',
        description: 'Confirm both source text and translated text appear in Subtitle Preview.',
      },
      {
        label: 'Export SRT',
        description: 'Finish by exporting SRT (.srt) and confirming the selected single or bilingual mode.',
      },
    ],
    uninstallAvailability: 'Windows uninstall is available',
    useUninstallPanelAction: 'Use Uninstall Panel',
    uninstallWarningTitle: 'Confirm before uninstalling',
    uninstallWarningDescription:
      'Uninstalling closes the current app and hands off the rest of the process to the Windows uninstaller.',
    uninstallStatusTitle: 'Uninstall flow',
    uninstallHelper:
      'Save the current subtitle edits and export results first, then continue with uninstall when you are ready.',
    uninstallCleanupTitle: 'Managed model cleanup',
    uninstallCleanupDescription:
      'During a real uninstall, LinguaSub also removes only its own downloaded speech models. Files outside LinguaSub-owned model storage stay untouched.',
    uninstallErrorTitle: 'Uninstall failed to start',
    uninstallCloseReminder: 'LinguaSub will close automatically after confirmation.',
    uninstallingHint:
      'LinguaSub is closing and preparing to launch the Windows uninstaller.',
    uninstallConfirmTitle: 'Confirm uninstall',
    uninstallConfirmDescription:
      'LinguaSub will close first. The Windows uninstaller will then remove the app and safely clean only LinguaSub-managed speech models.',
    managedModelRootsTitle: 'Managed model roots',
    managedModelRootsDescription:
      'Only the LinguaSub-owned folders listed here are eligible for automatic cleanup.',
    managedModelRootsEmpty: 'No LinguaSub-managed model root is recorded yet.',
    uninstallManagedRootsIntro:
      'These are the exact LinguaSub-owned model roots that uninstall may clean if recorded model folders are present.',
    removeModelsOption: 'Also remove downloaded local models',
    removeModelsSafeTitle: 'Safety protection',
    removeModelsSafeDescription:
      'Only LinguaSub-managed model folders are removed. LinguaSub never deletes the broader parent folder you selected, and legacy or unmanaged model files outside its owned model roots are protected.',
    cancelUninstallAction: 'Cancel',
    confirmUninstallAction: 'Start Uninstall',
    uninstallConfirm:
      'Do you want to uninstall LinguaSub?\n\nThis will close the current app and start the Windows uninstaller.',
  },
}

const zhMessagesNormalized = {
  ...zhMessages,
  common: {
    ...zhMessages.common,
    buttons: {
      ...zhMessages.common.buttons,
      exportWord: '导出 Word',
    },
    exportFormats: {
      srt: 'SRT',
      word: 'Word',
      recognition_text: '识别原文 TXT',
    },
    wordExportModes: {
      bilingualTable: '双语表格',
      transcript: '逐段文稿',
    },
    asrLanguages: {
      auto: '自动识别',
      zh: '中文',
      en: '英文',
      ja: '日文',
      ko: '韩文',
    },
    asrQualityPresets: {
      speed: '速度优先',
      balanced: '平衡',
      accuracy: '准确率优先',
    },
  },
  app: {
    ...zhMessages.app,
    workspace: {
      ...zhMessages.app.workspace,
      export: {
        title: '导出结果',
        description: '选择导出类型，确认少量选项后生成文件。',
      },
    },
    errors: {
      ...zhMessages.app.errors,
      cloudTranscriptionSetupRequired:
        'Cloud transcription still needs API configuration. Open Settings and save the OpenAI Speech-to-Text base URL, API key, and model first.',
      translationApiSetupRequired:
        '默认翻译服务还没有完成 API 配置。请先到设置页填写并保存 provider、base URL、API Key 和 model。',
    },
  },
  importPage: {
    ...zhMessages.importPage,
    environment: {
      ...zhMessages.importPage.environment,
      models: {
        ...zhMessages.importPage.environment.models,
        languageLabel: '识别语言',
        languageHint:
          '如果你已经知道素材语言，优先在这里明确指定，能减少识别成错误语言的情况。',
        qualityLabel: '识别质量',
        qualityDescriptions: {
          speed: '适合干净音频的快速预览，解码更轻，字幕整理也更少。',
          balanced:
            '推荐默认项。在速度和准确率之间更平衡，会额外做字幕可读性整理。',
          accuracy:
            '适合较难、较吵的音频。会使用更强的解码和更严格的断句，但 CPU 上会更慢。',
        },
        customStorageDescription:
          '选择一个父目录。LinguaSub 会在里面创建专属的 LinguaSub\\Models 子目录来保存模型。',
        customPathPlaceholder: '例如 D:\\AIAssets',
      },
    },
  },
  translationPage: {
    ...zhMessages.translationPage,
    apiConfigNeededTitle: '需要先配置翻译 API',
    apiConfigNeededDescription:
      '开始翻译前，请先在设置页填写并保存 provider、base URL、API Key 和 model。',
    openSettingsAction: '打开设置',
    recognitionSummaryTitle: '识别质量摘要',
    recognitionSummarySettings: (
      modelSize: string,
      qualityPreset: string,
      language: string,
    ) => `当前识别计划：${modelSize} 模型 · ${qualityPreset} · ${language}。`,
    rawQualitySummary: (
      modelSize: string,
      qualityPreset: string,
      requestedLanguage: string,
      detectedLanguage: string,
    ) =>
      `原始识别质量主要取决于 ${modelSize} 模型、${qualityPreset} 档位，以及“${requestedLanguage}”语言提示。本次检测到的语言：${detectedLanguage}。`,
    readabilitySummary: (rawCount: number, finalCount: number) =>
      `字幕可读性整理把 ${rawCount} 个原始片段整理成了 ${finalCount} 条更适合阅读的字幕。`,
    translationBoundaryNote:
      '翻译质量是另一层问题。如果这里的原文字幕已经不准，请先回头调整识别设置，不要直接把问题归到翻译上。',
    rawQualityPending:
      '识别开始后，原始识别质量会取决于所选模型、质量档位和语言提示。',
    readabilityPending:
      '识别返回后，LinguaSub 会再做轻量的断句和清洗，让字幕更适合阅读。',
  },
  previewPage: {
    ...zhMessages.previewPage,
    agent: {
      eyebrow: 'Agent',
      title: '字幕智能 Agent',
      description: '基于当前字幕生成质量诊断和内容总结，不会自动修改原字幕。',
      emptyTitle: '暂无字幕内容',
      emptyDescription: '暂无字幕内容，请先完成识别或导入字幕。',
      configError: '请先在设置中配置翻译模型 API。',
      qualityError: '字幕质量诊断失败，请重试。',
      summaryError: '内容总结生成失败，请重试。',
      actions: {
        analyzeQuality: 'AI 诊断字幕质量',
        analyzingQuality: '诊断中...',
        generateSummary: '生成内容总结',
        generatingSummary: '生成中...',
      },
      qualityTitle: '质量诊断',
      qualityDescription: '检查翻译、时间轴、阅读长度和双语格式等问题。',
      scoreLabel: '分',
      issuesTitle: '问题列表',
      noIssues: '未发现明显问题。',
      summaryTitle: '内容总结',
      summaryDescription: '从当前字幕生成面向学习和复盘的结构化总结。',
      oneSentenceTitle: '一句话总结',
      chaptersTitle: '分段章节',
      keywordsTitle: '关键词 / 专有名词',
      studyNotesTitle: '学习笔记',
      noChapters: '暂无章节总结。',
      noKeywords: '暂无关键词。',
      severities: {
        info: '提示',
        warning: '警告',
        error: '错误',
      },
      issueTypes: {
        empty_translation: '空翻译',
        missing_translation: '漏翻',
        timing_error: '时间轴异常',
        too_long: '字幕过长',
        bilingual_format_error: '双语格式异常',
        terminology_inconsistent: '术语不一致',
        unnatural_translation: '翻译不自然',
      },
    },
  },
  exportPage: {
    ...zhMessages.exportPage,
    sections: {
      ...zhMessages.exportPage.sections,
      export: {
        ...zhMessages.exportPage.sections.export,
        title: '导出结果',
        description:
          '选择导出类型，确认少量选项后生成文件。',
      },
    },
    task: {
      targetLabel: '导出类型',
      targets: {
        subtitle: {
          title: '字幕文件',
          description: '把当前字幕片段导出为 SRT 文件。',
        },
        recognitionText: {
          title: '识别原文 TXT',
          description: '导出语音识别得到的原始文本，便于人工检查识别准确性。',
        },
        word: {
          title: 'Word 文档',
          description: '生成适合审阅、阅读或归档的 DOCX 文件。',
        },
        video: {
          title: '带字幕视频',
          description: '把字幕烧录到原视频上，另存为新的 MP4。',
        },
      },
      fileNameLabel: '文件名',
      fileNameHint: '留空时会使用默认名称。',
      videoStyleTitle: '视频样式',
      videoStyleDescription: '自动适配竖屏 / 横屏。',
      videoSourceLabel: '原视频',
      noOriginalVideo: '当前没有原视频路径，请先从“视频字幕”生成字幕。',
      noSegments: '当前还没有字幕内容，请先完成识别或翻译。',
      successTitle: '导出完成',
      failureTitle: '导出失败',
      failureHint: '请检查路径、权限或设置后重试。',
      outputPathLabel: '已保存到：',
      openFolder: '打开所在目录',
      detailsTitle: '查看导出详情',
      projectSummaryTitle: '项目摘要',
      formatDetailsTitle: '格式说明',
      outputRulesTitle: '输出规则',
      videoNotesTitle: '视频导出',
      outputRulesDescription:
        '字幕和 Word 默认保存到源文件所在目录。带字幕视频会先让你选择完整的 MP4 保存路径。',
      videoNotesDescription:
        '带字幕视频会使用当前完整 ProjectState.segments，并由后端自动选择适合竖屏 / 横屏的字幕样式。',
      buttons: {
        exportSubtitle: '导出字幕文件',
        exportRecognitionText: '导出识别原文 TXT',
        exportWord: '导出 Word 文档',
        exportVideo: '导出带字幕视频',
        exporting: '正在导出...',
        exportingVideo: '正在生成带字幕视频...',
      },
    },
    formatLabel: '导出格式',
    wordModeLabel: 'Word 模式',
    fileFormatValues: {
      srt: 'SRT (.srt)',
      word: 'Word (.docx)',
      recognition_text: '识别原文 TXT (.txt)',
    },
    fileFormatDescriptions: {
      srt:
        'SRT 导出会保留字幕时间轴结构，并按当前单双语模式写出字幕内容。',
      word:
        'Word 导出会生成真正的 .docx 文件，可在双语表格和可读文稿两种布局之间切换。',
      recognition_text:
        'TXT 导出只写入带时间戳的识别原文，用于人工检查语音识别准确性。',
    },
    wordModeDescriptions: {
      bilingualTable:
        '双语表格模式会把每条字幕写成一行，包含开始时间、结束时间、原文和译文四列。',
      transcript:
        '逐段文稿模式会按时间顺序把每条字幕写成更适合阅读的段落，保留时间信息、原文和译文。',
    },
    writingDescription: '后端正在生成所选格式的导出文件并保存到磁盘。',
    readyDescription: (exportFormatLabel: string) =>
      `点击下方主按钮即可生成 ${exportFormatLabel} 文件。`,
    wordMissingTranslationsDescription: (count: number) =>
      `${count} 条字幕还没有译文。Word 导出会保留这些行，并让译文单元格保持空白。`,
    wordInvalidTimelineDescription: (count: number) =>
      `${count} 条字幕的时间信息缺失或异常。Word 导出会继续保留这些行，并在需要时写入安全的时间占位符。`,
    extensionTitle: '输出文件扩展名',
    extensionDescriptions: {
      srt:
        'SRT 导出始终生成 .srt 文件。双语模式和单语模式都会使用同一个 SRT 容器格式。',
      wordBilingualTable:
        'Word 导出会生成 .docx 文件，当前内容是适合学习、审阅和归档的双语表格。',
      wordTranscript:
        'Word 导出会生成 .docx 文件，当前内容是带时间信息的可读文稿，适合通读和整理。',
    },
  },
  settingsPage: {
    ...zhMessages.settingsPage,
    sections: {
      ...zhMessages.settingsPage.sections,
      settings: {
        ...zhMessages.settingsPage.sections.settings,
        title: 'API 配置与应用设置',
        description:
          '把翻译真正可用所需的 provider、base URL、API Key 和 model 都集中放在这里，保存后会立即刷新当前可用状态。',
      },
      verification: {
        eyebrow: '验证',
        title: '推荐验证路径',
        description: '用最短流程确认翻译是否真的可用，不必先依赖本地语音识别。',
      },
    },
    labels: {
      ...zhMessages.settingsPage.labels,
      apiStatus: 'API 配置状态',
      activeProvider: '当前默认服务商',
    },
    apiAvailable: '已可用于翻译',
    apiMissing: '尚未可用',
    apiAvailableDescription:
      '当前默认服务商已经具备可保存、可验证、可发起翻译的基础配置。',
    apiMissingDescription:
      '还没有完整 API 配置时，翻译会失败。请先保存并验证配置。',
    activeProviderDescription:
      '这里显示保存后的默认翻译服务商，翻译页会直接复用它。',
    baseUrlHelper:
      '填写服务商的 Chat Completions 基础地址，例如 OpenAI 兼容接口或 DeepSeek 的 /v1 地址。',
    apiKeyPlaceholder: '输入你的 API Key',
    apiKeyHelper:
      'API Key 保存在本地 JSON 配置中。保存后可立即点击“验证配置”测试是否可连通。',
    outputModeDescription:
      '这里设置默认导出模式。导出页仍可临时切换，但保存后会成为下次启动的默认值。',
    saveAction: '保存配置',
    saving: '保存中...',
    validateAction: '验证配置',
    validating: '验证中...',
    saveSuccessTitle: '配置已保存',
    saveSuccess: '翻译设置已写入本地配置，并已刷新当前可用状态。',
    saveFailed: '保存配置失败，请稍后再试。',
    validationSuccessTitle: '连接验证通过',
    validationFailed:
      '配置验证失败，请检查 provider、base URL、API Key 和 model。',
    apiConfigErrorTitle: 'API 配置有问题',
    nextVerificationTitle: '推荐下一步',
    nextVerificationDescription:
      '下一步建议直接导入一个 SRT 文件来验证翻译。这样可以跳过本地转录，最快确认 API 翻译链路是否正常。',
    goToImportAction: '导入 SRT 验证',
    bestVerificationTitle: '最快的验证方式',
    bestVerificationDescription:
      '优先导入一个现成的 SRT 文件来验证翻译。这样可以跳过本地转录、FFmpeg、faster-whisper 和模型下载，只确认 API 翻译本身是否工作。',
    verificationSteps: [
      {
        label: '保存 API 配置',
        description: '先在这里填写 provider、base URL、API Key 和 model，并点击保存。',
      },
      {
        label: '导入 SRT',
        description: '用 SRT 路线直接验证翻译，不依赖本地语音识别。',
      },
      {
        label: '开始翻译',
        description: '进入翻译页启动翻译，检查是否能正常返回 translatedText。',
      },
      {
        label: '检查预览',
        description: '在字幕预览页确认原文和译文是否都出现了。',
      },
      {
        label: '导出 SRT',
        description: '最后在导出页确认 SRT (.srt) 输出和单双语模式是否符合预期。',
      },
    ],
    useUninstallPanelAction: '请使用下方卸载面板',
    uninstallCleanupTitle: '可选的模型清理',
    uninstallCleanupDescription:
      '卸载时也可以一并删除已下载的本地语音模型，但 LinguaSub 只会删除自己能确认拥有的模型目录。',
    uninstallConfirmTitle: '确认卸载',
    uninstallConfirmDescription:
      'LinguaSub 会先关闭当前应用，然后交给 Windows 继续执行卸载流程。',
    removeModelsOption: '同时删除已下载的本地模型',
    removeModelsSafeTitle: '安全保护说明',
    removeModelsSafeDescription:
      '只会删除 LinguaSub 自己管理的模型目录。不会删除你选择的父目录，也不会删除模型根目录之外的无关文件。',
    cancelUninstallAction: '取消',
    confirmUninstallAction: '开始卸载',
  },
} as const

export const messages = {
  zh: zhMessagesNormalized,
  en: enMessages,
}

export function isUiLanguage(value: string): value is UiLanguage {
  return value === 'zh' || value === 'en'
}

// To extend the UI to Japanese or Korean later:
// 1. Add a new language code to UiLanguage.
// 2. Copy one existing message set and translate the values.
// 3. Add the new option to the language switch UI in StepHeader.
