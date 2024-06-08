The "global-rebasing" process is the process where all feature branches are
rebased on each other until generating the final repository.

We need to have a list of branches to rebase on top of. For example, we have:
feature5
feature4
feature3
feature2
feature1
So, feature 2 rebases on top of feature1, feature3 rebases on top feature2, and so on ...

When a feature, let's say feature1, enters into reviewing mode due to a merge request;
feature1 is not going to be sent upstream but a new branch called feature1-reviewing.

The process of generating the final branch will still be the rebasing against all feature
branches, but feature1 is marked as "merging" in the file.

Once all fixups, rebases, etc of the feature branch going upstream are done, the branch is
marked as "merged", so the "global-rebasing" process is done by skipping feature1 but ontop
of a new main, the one with feature1-reviewing merged.

Features
[ ] Keep a backup branch on each "global-rebasing" process (Option)
[ ] "Global-rebasing" as a command (Command)
[ ] Generate a markdown graph of the tree
