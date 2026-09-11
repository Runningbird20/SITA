import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusDot } from "./StatusDot";

describe("StatusDot", () => {
  it.each([
    ["implemented", "Working"],
    ["implemented_static", "Implemented"],
    ["not_implemented", "Not implemented"],
    ["broken", "Broken"],
    ["checking", "Checking…"],
  ] as const)("shows %s as %s", (status, label) => {
    render(<StatusDot status={status} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it("stamps the status as a data attribute for styling", () => {
    const { container } = render(<StatusDot status="broken" />);
    expect(container.querySelector('[data-status="broken"]')).toBeInTheDocument();
  });
});
