import typing_extensions as typing


class SocialMediaLinks(typing.TypedDict, total=False):
    linkedin: str
    github: str
    portfolio: str
    otherSocialMediaLinks: list[str]


class WorkExperience(typing.TypedDict):
    title: str
    company: str
    durationMonths: int
    description: str


class Project(typing.TypedDict):
    name: str
    durationMonths: int
    description: str
    link: str


class DomainExperience(typing.TypedDict):
    domain: str
    months: int


class Education(typing.TypedDict, total=False):
    degree: str
    institution: str
    startDate: str
    endDate: str
    description: str


class ResumeOutput(typing.TypedDict):
    name: str
    email: str
    socialMediaLinks: SocialMediaLinks
    workExperience: list[WorkExperience]
    projects: list[Project]
    education: list[Education]
    skillsAndTechnologies: list[str]
    monthsOfWorkExperienceByDomain: list[DomainExperience]
    otherInfo: str
