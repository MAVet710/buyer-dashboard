# Advisory performance review

Measured 2026-09-19. Raw observations and asset names are in `performance-measurements.json` beside this document.

## Method and limits

Compared the active release recorded in `.local/public-host.json` (`20260919T162253Z-beta/dist`) with the newly built `frontend/dist`. Used installed headless Chrome, a 1440 × 1000 viewport, three fresh browser contexts per route, and local filesystem-backed response interception for `https://doobielogic.io`. Browser contexts had no prior cache or consent; service workers were blocked. Requests never reached the public site. The consulting booking request received an inert unavailable response.

JavaScript and CSS totals below are exact response body bytes fulfilled for the observed route, counted once per asset. They exclude HTML, images, fonts and HTTP headers. The gzip column is the sum of independently gzip-compressed asset bodies calculated locally, **not observed production transfer size**. Intercepted responses were uncompressed. No bandwidth or CPU throttling was applied. These are desktop cold-context lab timings, not mobile Lighthouse scores, field Core Web Vitals, production TTFB, or a prediction of user latency. Shared OS/browser binary caches were not flushed. FCP and LCP are medians of three runs, measured through browser performance entries; small differences are noise.

## Results

| Route/build | JS body bytes | CSS body bytes | Estimated gzip JS + CSS | Median FCP | Median LCP |
| --- | ---: | ---: | ---: | ---: | ---: |
| Active baseline homepage | 446,507 | 168,635 | 170,634 | 56 ms | 444 ms |
| New homepage | 466,070 | 171,883 | 179,344 | 56 ms | 436 ms |
| New /consulting | 470,747 | 174,955 | 182,014 | 60 ms | 412 ms |
| New days-on-hand resource | 470,747 | 174,955 | 182,014 | 60 ms | 396 ms |
| New inventory health tool | 456,869 | 174,955 | 178,127 | 60 ms | 400 ms |

Homepage delta: +19,563 JavaScript bytes (+4.38%), +3,248 CSS bytes (+1.93%), and +8,710 estimated gzip bytes (+5.10%). Combined uncompressed JS/CSS increases from 615,142 to 637,953 bytes (+3.71%). The existing homepage H1 is identical in both runs. The three baseline LCP observations were 468/444/432 ms; new homepage observations were 444/428/436 ms. This small local sample did not exhibit slower median paint, but it is insufficient to claim no material production regression. The increased payload is real.

## Dependency correction

The first advisory build put service descriptions and all three article bodies in a shared `consultingContent` chunk of 21,495 bytes. The homepage imported its service cards from that module, so it unnecessarily loaded the article text.

Split service records into `consultingServices.ts`. `consultingContent.ts` re-exports the previous service API for compatibility; the homepage imports the service-only module directly. Article bodies now live in the lazy `ConsultingPages` chunk. The measured homepage asset list contains `consultingServices` and does **not** contain `ConsultingPages` or any resource article bodies. The SEO registry also imports no long-form resources. TypeScript and the production build passed after this change.

The consulting hub still shares its lazy chunk with resource pages, so its request loads all three articles. This is a bounded remaining opportunity: split article metadata from full article bodies and lazy-load article pages if the library grows. The current task fixes the homepage path without introducing more asynchronous page state.

## Release follow-up

Validate actual compression/cache headers and production mobile performance after deployment. Keep the numeric baseline when evaluating future additions. No claim of a Lighthouse score or field performance pass is made here.
