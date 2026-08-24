import { BRAND_IMAGE_URL } from "../lib/brand";

export function BrandLogo({ className = "brand-logo-image", alt = "DoobieLogic" }: { className?: string; alt?: string }) {
  return <img className={className} src={BRAND_IMAGE_URL} alt={alt} />;
}
