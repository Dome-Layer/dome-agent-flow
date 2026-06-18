"use client";

import Link from "next/link";
import { ToolHeader } from "@dome-layer/dome-ui";

const navLinks = [{ label: "Approvals", href: "/" }];

function renderLink(props: {
  href: string;
  children: React.ReactNode;
  className?: string;
  style?: React.CSSProperties;
  "aria-label"?: string;
  onClick?: () => void;
}) {
  return (
    <Link
      href={props.href}
      className={props.className}
      style={props.style}
      aria-label={props["aria-label"]}
      onClick={props.onClick}
    >
      {props.children}
    </Link>
  );
}

export function NavHeader() {
  return <ToolHeader toolName="Agent Flow" renderLink={renderLink} navLinks={navLinks} />;
}
