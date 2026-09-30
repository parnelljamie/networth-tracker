import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { useEffect } from "react"
import { BrowserRouter, Route, Routes } from "react-router"
import { AppLayout } from "@/components/layout/AppLayout"
import { Toaster } from "@/components/ui/sonner"
import { toggleCommandPalette } from "@/lib/commandPalette"
import { togglePrivacyMode } from "@/lib/privacy"
import { AccountDetail } from "@/pages/AccountDetail"
import { Goals } from "@/pages/Goals"
import { Import } from "@/pages/Import"
import { Investments } from "@/pages/Investments"
import { OtherAssets } from "@/pages/OtherAssets"
import { Overview } from "@/pages/Overview"
import { Pensions } from "@/pages/Pensions"
import { Person } from "@/pages/Person"
import { Projections } from "@/pages/Projections"
import { Property } from "@/pages/Property"
import { Settings } from "@/pages/Settings"

const queryClient = new QueryClient()

function usePrivacyShortcut() {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.shiftKey && event.key.toLowerCase() === "p") {
        const target = event.target as HTMLElement | null
        if (target && ["INPUT", "TEXTAREA"].includes(target.tagName)) return
        togglePrivacyMode()
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [])
}

function useCommandPaletteShortcut() {
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      // Ctrl+K (Cmd+K on Mac) opens the command palette from anywhere, including from within
      // inputs — it's the global launcher, unlike the privacy shortcut.
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault()
        toggleCommandPalette()
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [])
}

function App() {
  usePrivacyShortcut()
  useCommandPaletteShortcut()

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<AppLayout />}>
            <Route index element={<Overview />} />
            <Route path="people/:id" element={<Person />} />
            <Route path="accounts/:id" element={<AccountDetail />} />
            <Route path="property" element={<Property />} />
            <Route path="pensions" element={<Pensions />} />
            <Route path="investments" element={<Investments />} />
            <Route path="other" element={<OtherAssets />} />
            <Route path="projections" element={<Projections />} />
            <Route path="goals" element={<Goals />} />
            <Route path="import" element={<Import />} />
            <Route path="settings" element={<Settings />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster />
    </QueryClientProvider>
  )
}

export default App
