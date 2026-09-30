import * as React from "react"
import { cn } from "cn"

/**
 * Ledger (docs/05-ui.md "Shape"): a card is a ruled section by default — a 2 px ink rule on top
 * and no box, so the page reads like a statement. `variant="boxed"` gives a paper card for
 * tiles that sit in a grid (account cards, goals, other assets).
 */
function Card({
  className,
  size = "default",
  variant = "ruled",
  ...props
}: React.ComponentProps<"div"> & { size?: "default" | "sm"; variant?: "ruled" | "boxed" }) {
  return (
    <div
      data-slot="card"
      data-size={size}
      data-variant={variant}
      className={cn(
        "group/card flex flex-col gap-(--card-spacing) text-sm text-card-foreground [--card-spacing:--spacing(4)] data-[size=sm]:[--card-spacing:--spacing(3)]",
        "data-[variant=ruled]:border-t-2 data-[variant=ruled]:border-ink data-[variant=ruled]:pt-3 data-[variant=ruled]:[--card-inset:0px]",
        "data-[variant=boxed]:overflow-hidden data-[variant=boxed]:rounded-xl data-[variant=boxed]:border data-[variant=boxed]:border-border data-[variant=boxed]:bg-card data-[variant=boxed]:py-(--card-spacing) data-[variant=boxed]:[--card-inset:--spacing(5)]",
        className
      )}
      {...props}
    />
  )
}

function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-header"
      className={cn(
        "group/card-header @container/card-header grid auto-rows-min items-baseline gap-1 px-(--card-inset) has-data-[slot=card-action]:grid-cols-[1fr_auto] has-data-[slot=card-description]:grid-rows-[auto_auto] [.border-b]:pb-(--card-spacing)",
        className
      )}
      {...props}
    />
  )
}

function CardTitle({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-title"
      className={cn(
        "font-heading text-2xl leading-tight font-medium tracking-[-0.01em] text-ink group-data-[size=sm]/card:text-xl group-data-[variant=boxed]/card:text-xl",
        className
      )}
      {...props}
    />
  )
}

function CardDescription({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-description"
      className={cn("text-sm text-muted-foreground", className)}
      {...props}
    />
  )
}

function CardAction({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-action"
      className={cn(
        "col-start-2 row-span-2 row-start-1 self-start justify-self-end",
        className
      )}
      {...props}
    />
  )
}

function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-content"
      className={cn("px-(--card-inset)", className)}
      {...props}
    />
  )
}

function CardFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-footer"
      className={cn(
        "flex items-center border-t border-rule-soft px-(--card-inset) pt-(--card-spacing)",
        className
      )}
      {...props}
    />
  )
}

export {
  Card,
  CardHeader,
  CardFooter,
  CardTitle,
  CardAction,
  CardDescription,
  CardContent,
}
