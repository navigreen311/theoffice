/**
 * Tabler outline icons, inlined.
 *
 * Five paths rather than a dependency. `@tabler/icons-react` is several thousand
 * components for the five used here, and this console has hand-written its primitives
 * from the start for a related reason — `shadcn init` is an interactive CLI that hangs
 * in this environment, and that was recorded rather than silently substituted.
 *
 * Outline only. The `-filled` variants read as decoration, and every icon on the
 * compliance page is carrying state.
 *
 * Source: Tabler Icons (https://tabler.io/icons), MIT licence. Paths copied verbatim
 * from the outline set so they can be diffed against upstream.
 */
import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function Icon({ size = 18, children, ...props }: IconProps) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {children}
    </svg>
  );
}

/** ti-alert-triangle — the banner, and anything blocking. */
export function AlertTriangle(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 9v4" />
      <path d="M10.363 3.591l-8.106 13.534a1.914 1.914 0 0 0 1.636 2.871h16.214a1.914 1.914 0 0 0 1.636 -2.87l-8.106 -13.536a1.914 1.914 0 0 0 -3.274 0z" />
      <path d="M12 16h.01" />
    </Icon>
  );
}

/** ti-link-off — the audit chain, when it cannot be verified. */
export function LinkOff(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M9 15l3 -3m2 -2l1 -1" />
      <path d="M11 6l.463 -.536a5 5 0 0 1 7.071 7.072l-.534 .464" />
      <path d="M3 3l18 18" />
      <path d="M13 18l-.397 .534a5.068 5.068 0 0 1 -7.127 0a4.972 4.972 0 0 1 0 -7.071l.524 -.463" />
    </Icon>
  );
}

/** ti-certificate-off — certification staleness. */
export function CertificateOff(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12.983 8.978c.6 -.6 .995 -1.39 .995 -2.278a3.7 3.7 0 0 0 -3.7 -3.7c-.888 0 -1.677 .395 -2.278 .995" />
      <path d="M6.5 6.5a3.7 3.7 0 0 0 3.7 3.7c.888 0 1.677 -.395 2.278 -.995" />
      <path d="M6 10.6a3.7 3.7 0 0 1 -3.6 -3.6a3.7 3.7 0 0 1 3.6 -3.6" />
      <path d="M6 14v7l3 -2l3 2v-7" />
      <path d="M3 3l18 18" />
    </Icon>
  );
}

/** ti-list-check — manifest reconciliation. */
export function ListCheck(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M3.5 5.5l1.5 1.5l2.5 -2.5" />
      <path d="M3.5 11.5l1.5 1.5l2.5 -2.5" />
      <path d="M3.5 17.5l1.5 1.5l2.5 -2.5" />
      <path d="M11 6l9 0" />
      <path d="M11 12l9 0" />
      <path d="M11 18l9 0" />
    </Icon>
  );
}

/** ti-database-off — the restore drill. */
export function DatabaseOff(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12.983 8.978c3.955 -.182 7.017 -1.446 7.017 -2.978c0 -1.657 -3.582 -3 -8 -3c-1.661 0 -3.204 .19 -4.483 .515" />
      <path d="M4 6v6c0 1.657 3.582 3 8 3c.986 0 1.93 -.067 2.802 -.19" />
      <path d="M20 12v6" />
      <path d="M4 12v6c0 1.657 3.582 3 8 3c3.217 0 5.991 -.712 7.261 -1.74" />
      <path d="M3 3l18 18" />
    </Icon>
  );
}

/** ti-circle-check — a verified control, and the quiet success banner. */
export function CircleCheck(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 12m-9 0a9 9 0 1 0 18 0a9 9 0 1 0 -18 0" />
      <path d="M9 12l2 2l4 -4" />
    </Icon>
  );
}

/** ti-file-export — the regulator export. */
export function FileExport(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M14 3v4a1 1 0 0 0 1 1h4" />
      <path d="M11.5 21h-4.5a2 2 0 0 1 -2 -2v-14a2 2 0 0 1 2 -2h7l5 5v5m-5 6h7m-3 -3l3 3l-3 3" />
    </Icon>
  );
}

/** ti-plus — create. */
export function Plus(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 5l0 14" />
      <path d="M5 12l14 0" />
    </Icon>
  );
}

/** ti-plug-off — a venture blocked because something it depends on does not exist. */
export function PlugOff(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M3 3l18 18" />
      <path d="M9.785 6h8.215v8m-3 3h-9v-9a3 3 0 0 1 3 -3" />
      <path d="M7 19v2" />
      <path d="M17 19v2" />
      <path d="M7 5v-2" />
      <path d="M17 5v-2" />
    </Icon>
  );
}

/** ti-dots — the overflow menu. */
export function Dots(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M5 12m-1 0a1 1 0 1 0 2 0a1 1 0 1 0 -2 0" />
      <path d="M12 12m-1 0a1 1 0 1 0 2 0a1 1 0 1 0 -2 0" />
      <path d="M19 12m-1 0a1 1 0 1 0 2 0a1 1 0 1 0 -2 0" />
    </Icon>
  );
}

/** ti-external-link — open. */
export function ExternalLink(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M12 6h-6a2 2 0 0 0 -2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2 -2v-6" />
      <path d="M11 13l9 -9" />
      <path d="M15 4h5v5" />
    </Icon>
  );
}

/** The icon for a control, by id. Unknown ids get the loudest one on purpose. */
export const CONTROL_ICON: Record<
  string,
  (props: IconProps) => JSX.Element
> = {
  audit_chain: LinkOff,
  certification_staleness: CertificateOff,
  manifest_reconciliation: ListCheck,
  restore_drill: DatabaseOff,
};

/** tabler: copy */
export function Copy(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M7 7m0 2.667a2.667 2.667 0 0 1 2.667 -2.667h8.666a2.667 2.667 0 0 1 2.667 2.667v8.666a2.667 2.667 0 0 1 -2.667 2.667h-8.666a2.667 2.667 0 0 1 -2.667 -2.667z" />
      <path d="M4.012 16.737a2 2 0 0 1 -1.012 -1.737v-10c0 -1.1 .9 -2 2 -2h10c.75 0 1.158 .385 1.5 1" />
    </Icon>
  );
}

/** tabler: git-compare */
export function GitCompare(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M6 6m-3 0a3 3 0 1 0 6 0a3 3 0 1 0 -6 0" />
      <path d="M18 18m-3 0a3 3 0 1 0 6 0a3 3 0 1 0 -6 0" />
      <path d="M11 6h5a2 2 0 0 1 2 2v7" />
      <path d="M14 9l-3 -3l3 -3" />
      <path d="M13 18h-5a2 2 0 0 1 -2 -2v-7" />
      <path d="M10 15l3 3l-3 3" />
    </Icon>
  );
}

/** tabler: file-text */
export function FileText(props: IconProps) {
  return (
    <Icon {...props}>
      <path d="M14 3v4a1 1 0 0 0 1 1h4" />
      <path d="M17 21h-10a2 2 0 0 1 -2 -2v-14a2 2 0 0 1 2 -2h7l5 5v11a2 2 0 0 1 -2 2z" />
      <path d="M9 9l1 0" />
      <path d="M9 13l6 0" />
      <path d="M9 17l6 0" />
    </Icon>
  );
}
