import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Pagination } from "./Pagination";

describe("Pagination", () => {
  it("renders nothing when there are no results", () => {
    const { container } = render(
      <Pagination total={0} limit={25} offset={0} onOffsetChange={vi.fn()} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the current range and disables Previous on the first page", () => {
    render(<Pagination total={60} limit={25} offset={0} onOffsetChange={vi.fn()} />);
    expect(screen.getByText("1–25 of 60")).toBeInTheDocument();
    expect(screen.getByText("Previous")).toBeDisabled();
    expect(screen.getByText("Next")).not.toBeDisabled();
  });

  it("disables Next on the last page, even a partial one", () => {
    render(<Pagination total={60} limit={25} offset={50} onOffsetChange={vi.fn()} />);
    expect(screen.getByText("51–60 of 60")).toBeInTheDocument();
    expect(screen.getByText("Next")).toBeDisabled();
    expect(screen.getByText("Previous")).not.toBeDisabled();
  });

  it("advances by limit when Next is clicked", async () => {
    const onOffsetChange = vi.fn();
    render(<Pagination total={60} limit={25} offset={0} onOffsetChange={onOffsetChange} />);
    screen.getByText("Next").click();
    expect(onOffsetChange).toHaveBeenCalledWith(25);
  });
});
