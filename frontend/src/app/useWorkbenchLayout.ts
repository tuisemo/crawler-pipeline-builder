import { useEffect, useState } from 'react'
import {
  WORKBENCH_LAYOUT_STORAGE_KEY,
  loadWorkbenchLayoutState,
  type DockTabKey,
} from '../features/workflow/workbenchDefaults'

export function useWorkbenchLayout() {
  const [initialWorkbenchLayout] = useState(() => loadWorkbenchLayoutState())
  const [leftPanelOpen, setLeftPanelOpen] = useState(initialWorkbenchLayout.leftPanelOpen)
  const [rightPanelOpen, setRightPanelOpen] = useState(initialWorkbenchLayout.rightPanelOpen)
  const [bottomDockOpen, setBottomDockOpen] = useState(initialWorkbenchLayout.bottomDockOpen)
  const [activeDockTab, setActiveDockTab] = useState<DockTabKey>(initialWorkbenchLayout.activeDockTab)
  const [workspaceVisibilityToken, setWorkspaceVisibilityToken] = useState(0)

  useEffect(() => {
    if (typeof window === 'undefined') return
    try {
      window.localStorage.setItem(WORKBENCH_LAYOUT_STORAGE_KEY, JSON.stringify({
        leftPanelOpen,
        rightPanelOpen,
        bottomDockOpen,
        activeDockTab,
      }))
    } catch {
      // Storage failures should never break the workbench itself.
    }
  }, [activeDockTab, bottomDockOpen, leftPanelOpen, rightPanelOpen])

  function refreshWorkspaceVisibility() {
    setWorkspaceVisibilityToken((current) => current + 1)
  }

  function openDockTab(tab: DockTabKey) {
    setBottomDockOpen(true)
    setActiveDockTab(tab)
  }

  function openResultsDock() {
    openDockTab('results')
  }

  function closeBottomDock() {
    setBottomDockOpen(false)
  }

  function selectDockTab(tab: DockTabKey) {
    setActiveDockTab(tab)
    refreshWorkspaceVisibility()
  }

  function handleDockOpenChange(open: boolean) {
    if (open) refreshWorkspaceVisibility()
  }

  return {
    leftPanelOpen,
    rightPanelOpen,
    bottomDockOpen,
    activeDockTab,
    workspaceVisibilityToken,
    setLeftPanelOpen,
    setRightPanelOpen,
    setBottomDockOpen,
    setActiveDockTab,
    openDockTab,
    openResultsDock,
    closeBottomDock,
    selectDockTab,
    handleDockOpenChange,
  }
}
