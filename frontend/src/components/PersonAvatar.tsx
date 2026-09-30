import { Avatar, AvatarFallback } from "@/components/ui/avatar"
import { cn } from "@/lib/utils"

interface PersonAvatarProps {
  name: string
  color?: string | null
  size?: "sm" | "md"
  className?: string
}

export function PersonAvatar({ name, color, size = "md", className }: PersonAvatarProps) {
  const initial = name.trim().charAt(0).toUpperCase() || "?"
  return (
    <Avatar className={cn(size === "sm" ? "size-5" : "size-7", className)}>
      <AvatarFallback
        className="text-white"
        style={{ backgroundColor: color ?? "var(--ink-muted)" }}
      >
        <span className={size === "sm" ? "text-[10px]" : "text-xs"}>{initial}</span>
      </AvatarFallback>
    </Avatar>
  )
}
