---
name: FAQ (Frequently Asked Questions)
description: Intended to explain aspects of the system to non-technical users, or to technical users who may lack expertise in certain areas, such as encryption.
Created: 2026-05-23
Revised: 2026-05-23
Status: In progress
---

# FAQ (Frequently Asked Questions)

This document is intended to help users of varying degrees of technical experience and knowledge understand how the system works, especially when such information is critical for understanding privacy and security boundaries, or making any decisions that might affect their data and how it is handled.

## Project overview

### Why are there so many repos?

(i) The primary objective is to give users their own designated repository that is equipped with everything they need to collect data about their repositories and analyze it with a useful HTML dashboard. So you can think of `reponomics-dashboard` as the primary product - a template repository that users can use to create their own repository with the aforementioned capabilities. But if everything lived within the template repository, there would be many problems - after repo creation, there is no inherent connection between a template repo and any repo created from it. Therefore, after using the template, the user would have to manage every aspect of the repo themselves - that means fixing bugs, security patches, some method for acquiring new features introduced at a later date, and so on.

(ii) So, in order to give users full control of their repository, without imposing undue maintenance burden, the template repo is meant to be a simple consumer for the `reponomics-dashboard-action`. The dashboard repos have workflows that consume the dashboard action, and it is the _action_ that implements the bulk of the functionality, including the scripts that collect and aggergate the other repositories' traffic and growth data, produces the rendered outputs such as the HTML dashboard and the README dashboard, orchestrate the encryption mechanisms that enable the dashboard to be rendered in a private manner, and many other responsibilities. Because the action and the repo are de-coupled, it is up to the user to determine whether, and how frequently, to adopt any changes that we introduce - since it's up to the user to determine which version of the action they want to use in their repo's workflows. And of course, the action source code is open for inspection.

(iii) In developing the template repository, naturally we wanted to include some "development stuff" - tests, additional CI/CD, additional documentation - things that an end user might not have any interest in. Our goal was to make `reponomics-dashoard` a polished, clean end-user product, not a construction site full of tests that they do not need to worry about (unless they have interest). So `reponomics-dashboard` is actually a _generated_ reop produced `reponomics-dashboard-dev` - this is the repo where all development work goes on, and where you can go if you want to judge the quality and security of the project that produces the template repo as an output.

(iv) Because the template repo looks pretty barren until you start to collect data, we maintain the `repository-dashoard-demo` repo as _another_ generated artifact that is intended to be a genuine demonstration of a repo created from the Reponomics dashboard template, with the only point of difference being that it does not collect data from the GitHub API, but rather contains its own mocked data for mock repositories. This is the best way to show users what they can expect after they start using the template repo.

(v) Finally, `reponomics` is the informational hub for the Reponomics organization that produces this product.

Summary:

- `reponomics-dashboard` is the real end user product, the template repo.
- `reponomics-dashboard-dev` is where the template repo gets built and maintained, in order to isolate development infrastructure from the finished product.
- `reponomics-dashboard-action` is the primary "engine" behind the dashboard, which serves as the bridge between the organization's ongoing development of the dashboard, and the user's own repo, making sure they stay in control of their own repo.
- `reponomics-dashboard-demo` is, well, a demo of how the Reponomics dashboard looks once it has collected some data.

## Privacy, Encryption, and Our Privacy Stance

### What are the different privacy modes and how do I decide which one I should use?

### What sort of password do I need and why does it have to be so long?

## What sort of threats does this system protect me from? And what does it leave me vulnerable to?

## Is any of my data committed to the repository's git history?

## Which entities have access to my repositories' data?

Ignoring attackers momentarily - if you have a README dashboard, then anyone with read access to your repository can see your data (or, at least, the latest metrics about your repositories, not necessarily every piece of data). Besides the README dashboard, if enabled, none of your repositories' data is ever stored anywhere within your repository. Instead, it lives in _workflow artifacts_, which are generated by the Reponomics dashboard action. Artifacts are stored in GitHub's artifact storage, not in your git history or in any directory in your repo. _However_, public repo artifacts are viewable by any GitHub user. They are retained for a configurable period of time, and during that time, they can be downloaded either from the website or from the GitHub API. For users who have opted for the "encrypted" track, the artifacts are encrypted before they are uploaded, then when the repo runs collection, the encrypted artifacts are download and decrypted within the workflow, and the new data is added, before they are encrypted again and uploaded. This is the only time in the entire lifecycle of the repo (ignoring the Pages site for a moment, since there is a clear boundary between the repo and the Pages site) that unencrypted data is handled by the repo - however, precautions are taken to ensure that this process cannot be inspected, logged, or captured by any curious party. It is a short-lived transaction which leaves no record behind of your unencrypted data. It's probably safer to think of artifact storage as "part of your repo" since artifacts can be viewed by those who have access to it, but otherwise we could say that your data is never anywhere in your repo at all, nor is it stored by any third party (excluding GitHub as a third party). Furthermore, unlike your git history, artifacts can be cleanly and permanently deleted, without leaving any traces in forked repos or "ghost refs".

So, on the assumption that you have encrypted your data with a strong password or secret, the only entities that have access to your data are those who have access to that secret, with one very important caveat - anyone who is able to run the secret-rotation workflow in your repository can replace your secret with anything they like - they do not need to know the previous secret. So the privacy boundary also includes anyone with such access, such as a collaborator. Not only do they have access to your data indirectly, a malicious collaborator could change the encryption key in such a way that you no longer have access to it anymore - so make sure you trust your collaborators.
