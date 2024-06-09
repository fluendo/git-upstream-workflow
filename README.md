## The workflow

The "global-rebasing" process is the process where all feature branches are
rebased on each other until generating the final repository.

We need to have a list of branches to rebase on top of. For example, we have:
```
o commit 11 [feature5, target]
o commit 10
o commit 9
o commit 8  [feature4]
o commit 7
o commit 6  [feature3]
o commit 5  [feature2]
o commit 4
o commit 3  [feature1]
o commit 2
o commit 1  [source]
```

So, feature 2 rebases on top of feature1, feature3 rebases on top of feature2, and so on ...

When a feature, let's say feature1, enters into reviewing mode due to a merge request;
feature1 is not going to be sent upstream but a new branch called feature1-reviewing.

```
o commit 3 [feature1, feature1-reviewing]
o commit 2
o commit 1 [source]
```

Usually, during that reviewing process, new commits might be added or removed, for example

```
o commit 3.2 [feature1-reviewing]
o commit 3.1
o commit 3   [feature1]
o commit 2
o commit 1   [source]
```

The process of generating the final branch will still be the rebasing against all feature
branches, but feature1 is marked as "merging" in the file.

Once all fixups, rebases, etc of the feature branch going upstream are done, the branch is
marked as "merged", so the "global-rebasing" process is done by skipping feature1 but on top
of a new main, the one with feature1-reviewing merged.


## Configuration file
```TOML
[[remotes]]
name = "origin"
url = "git@github.com:fluendo/git-upstream-workflow.git"

[target]
remote = "origin"
branch = "final"

[source]
remote = "origin"
branch = "main"

[[features]]
remote = "origin"
name = "feature1"
pr = "https://github/fluendo/git-upstream-workflow/pull-requests/10"
status = "integrated"

[[features]]
remote = "origin"
name = "feature2"
pr = "https://github/fluendo/git-upstream-workflow/pull-requests/10"
status = "merged"

[[features]]
remote = "origin"
name = "feature3"
status = "pending"
```

The configuration must include the list of remotes under the `[[remotes]]` section. This is useful
when the upstream branch is done in a git provider like GitLab but the development is done in GitHub.

There are two special sections, `[source]` and `[target]`. The `[source]` section defines the branch
the project you want to contribute to uses as the main stable branch.  The `[target]` section defines
the branch that should hold all the features.

The `[[features]]` section defines the list of features you want to include upstream (the `target` branch).
Each feature has the following key/value pairs:
`remote`
: The remote name as listed in the `[[remotes]]` section

`name`
: The name of the branch

`pr`
: The URL used for the merge-request/pull-request

`status`
: This defines how `guw` should handle the `sync` process.
: In case of `pending`, this branch is still not requested to be integrated on the upstream project.
: In case of `merging`, the branch has already opened a merge-request/pull-request and is waiting for the community to be reviewed.
: In case of `merged`, the branch has already being merged but the other features depending on this have not being rebased yet.
: In case of `integrated`, the dependant features have been rebased already and the actual feature is no longer considered in any process.

## Usage

## Recommendations
* Never push into the `target` branch by other means but through `guw`, otherwise your new commits will
  be lost after a `sync` process
