# Workflows for some common use cases 

## Add a new feature at the end of the feature list.

Manual actions to do by the developer:

* Create a new branch with the feature using the last feature as base.  
* Create a new PR with the new branch to get the review.  

Manual actions to do by the reviewer:

* Validate the PR

Automated actions done by GHA when the PR is approved.

* Execute guw `add` command.  
* Close PR with the feature with a comment to the guw PR merged.  

## Add a new feature in the middle of the features without conflict.

Similar to previous use case, but creating the new branch with the feature using the previous feature as base. If feature `foo` is created on top of feature `bar`, checkout from `bar`.  

## Remove a feature in the without a conflict

* Execute the guw `remove` command to remove the features and generate a new target.

## Add a new commit into a pending feature because of an internal requirement without conflict.

Manual actions to do by the developer:

* Create a new branch with the feature hotfix using the feature as base. If feature `foo` need to be updated, checkout a new branch `hox-hotfix1` from `foo`.  
* Create a new PR with the new branch

> [!IMPORTANT]
> Use the base branch as prefix of the new branch is mandatory to detect that it is not a new feature

Manual actions to do by the reviewer:

* Validate the PR

Automated actions done by GHA when the PR is approved.

* Close PR with a comment.  
* Execute the guw `update` command to sync the features and generate a new target.

## Change or delete a commit of a pending feature because of an internal requirement without conflict.

Similar to previous use case using a fixup commit to edit a previous commit of the feature or a revert commit to delete one. The goal is to make reviewing easier while ensuring a clean Git history after the review.  
When the PR is approved the feature will be rebased by squashing fixup commits (autosquash) by the guw `update` command.  

> [!IMPORTANT]
> Reverted commits also must be a fixup commit
>
> ```
> git revert --no-commit 1234
> git commit --fixup 1234
> ```
>
> Explanation https://stackoverflow.com/a/67739266


# Conflicts

TODO

