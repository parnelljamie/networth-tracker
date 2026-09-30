import { CATEGORY_ICONS, type Category } from "@/lib/categories"
import { cn } from "@/lib/utils"

interface CategoryIconProps {
  category: Category
  className?: string
}

export function CategoryIcon({ category, className }: CategoryIconProps) {
  const Icon = CATEGORY_ICONS[category]
  return <Icon className={cn("size-4", className)} aria-hidden="true" />
}
