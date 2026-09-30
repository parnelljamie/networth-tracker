import "@fontsource-variable/newsreader/opsz.css"
import "@fontsource-variable/newsreader/opsz-italic.css"
import "@fontsource-variable/public-sans/wght.css"
import "@fontsource/ibm-plex-mono/400.css"
import "@fontsource/ibm-plex-mono/500.css"
import "@/lib/theme"
import "@/styles/globals.css"

import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import App from "./App.tsx"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
)
