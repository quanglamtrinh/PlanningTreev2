// @ts-check
/**
 * Custom application menu for PlanningTree desktop app.
 */

const { app, Menu, shell, dialog } = require('electron')

/**
 * Build and return the application menu.
 * @param {{ mainWindow: import('electron').BrowserWindow, isDev: boolean, logPath: string }} opts
 * @returns {Electron.Menu}
 */
function buildMenu({ mainWindow, isDev, logPath }) {
  /** @type {Electron.MenuItemConstructorOptions[]} */
  const template = [
    {
      label: 'File',
      submenu: [{ role: 'quit', accelerator: 'CmdOrCtrl+Q' }],
    },
    {
      label: 'View',
      submenu: [
        ...(isDev
          ? [
              /** @type {Electron.MenuItemConstructorOptions} */
              ({ role: 'reload', accelerator: 'CmdOrCtrl+Shift+R' }),
              /** @type {Electron.MenuItemConstructorOptions} */
              ({ type: 'separator' }),
            ]
          : []),
        { role: 'togglefullscreen', accelerator: 'F11' },
        ...(isDev
          ? [
              /** @type {Electron.MenuItemConstructorOptions} */
              ({ type: 'separator' }),
              /** @type {Electron.MenuItemConstructorOptions} */
              ({ role: 'toggleDevTools', accelerator: 'CmdOrCtrl+Shift+I' }),
            ]
          : []),
      ],
    },
    {
      label: 'Help',
      submenu: [
        {
          label: 'Open Log File',
          click: () => shell.openPath(logPath),
        },
        {
          label: 'Open Data Folder',
          click: () => shell.openPath(app.getPath('userData')),
        },
        { type: 'separator' },
        {
          label: 'About PlanningTree',
          click: () => {
            dialog.showMessageBox(mainWindow, {
              type: 'info',
              title: 'About PlanningTree',
              message: 'PlanningTree',
              detail: [
                `Version: ${app.getVersion()}`,
                `Electron: ${process.versions.electron}`,
                `Node: ${process.versions.node}`,
                `Chrome: ${process.versions.chrome}`,
              ].join('\n'),
              buttons: ['OK'],
            })
          },
        },
      ],
    },
  ]

  return Menu.buildFromTemplate(template)
}

module.exports = { buildMenu }
