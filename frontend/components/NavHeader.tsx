"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ToolHeader } from "@dome-layer/dome-ui";

// The approvals queue is the home page, so it is the only nav item (no separate "Home" pointing at "/").
const navLinks = [{ label: "Approvals", href: "/" }];

function renderLink(props: {
  href: string;
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  "aria-label"?: string;
  "aria-current"?: "page";
  onClick?: () => void;
}) {
  return (
    <Link
      href={props.href}
      className={props.className}
      style={props.style}
      aria-label={props["aria-label"]}
      aria-current={props["aria-current"]}
      onClick={props.onClick}
    >
      {props.children}
    </Link>
  );
}

export function NavHeader() {
  const pathname = usePathname();

  return (
    <ToolHeader
      toolName="Agent Flow"
      showHomeLink={false}
      renderLink={renderLink}
      navLinks={navLinks}
      currentPath={pathname ?? undefined}
    />
  );
}
