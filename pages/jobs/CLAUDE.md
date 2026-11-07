# Jobs

`/jobs`, under Projects. The unchanged `new-view.py` scaffold was run in a
temporary staging directory while the Projects group was pending; only this
page was copied into the worktree. `tabs: projects` joins that group's rail.

Five native views: daytime tap, applications and record detail, cover letters,
screening questions, and the last eight runs with pacing and event detail.
`?view=applications&application=<stem>` opens an archived record directly.

`api.py` runs g-jobs' existing `gjobs.site.data` readers with its service's
`/usr/bin/python3` from the sibling `g-jobs` checkout (`GJOBS_DIR` overrides it).
Those readers resolve letters, answers, outcomes and pacing. Reads are fresh,
uncached and read-only. Every endpoint checks Command's `cookie_ok`, including
CV downloads; the original reader validates archive membership and this route
also confines the result to `out/variants`. There are no write actions in the
existing admin. Its site and service are unchanged.

Keep PageHead, Loaded, Empty, the shell gutter and transition. The page-specific
view-contract check is `python3 ~/g-levels/glevels/viewcontract.py . --page jobs`.
