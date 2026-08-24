import { render, screen } from "@testing-library/react";
import { SiteFooter } from "./site-footer";

describe("SiteFooter", () => {
  it("shows the copyright and links the ICP filing to MIIT", () => {
    render(<SiteFooter />);

    expect(screen.getByText("© 2026 Will")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "湘ICP备2026036121号-1" })).toHaveAttribute(
      "href",
      "https://beian.miit.gov.cn/",
    );
  });
});
