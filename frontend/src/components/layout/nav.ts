/** The main sections, in masthead order. People sits second as a menu of each person. */
export const SECTION_LINKS = [
  { to: "/property", label: "Property" },
  { to: "/pensions", label: "Pensions" },
  { to: "/investments", label: "Investments" },
  { to: "/other", label: "Other" },
  { to: "/projections", label: "Projections" },
  { to: "/goals", label: "Goals" },
]

export const TOOL_LINKS = [
  { to: "/import", label: "Import" },
  { to: "/settings", label: "Settings" },
]

/** Content column shared by the masthead and the page, so their edges line up. */
export const COLUMN = "mx-auto w-full max-w-[1440px] px-4 md:px-10 xl:px-16"
