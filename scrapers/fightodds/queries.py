"""GraphQL query strings for fightodds.io API."""

FIGHTODDS_GQL_URL = "https://api.fightodds.io/gql"

EVENTS_PAGE_QUERY = """
query EventsPageQuery(
  $count: Int!
  $cursor: String
  $dateGte: Date
  $dateLt: Date
  $orderBy: String
) {
  allEvents(
    first: $count
    after: $cursor
    date_Gte: $dateGte
    date_Lt: $dateLt
    orderBy: $orderBy
  ) {
    edges {
      node {
        id
        pk
        slug
        name
        date
        venue
        city
        promotion {
          slug
          shortName
        }
      }
      cursor
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
"""

EVENT_FIGHTS_QUERY = """
query EventFightsQuery($eventPk: Int) {
  event: eventByPk(pk: $eventPk) {
    pk
    slug
    name
    date
    promotion {
      slug
      shortName
    }
    fights {
      edges {
        node {
          pk
          slug
          order
          isCancelled
          fighter1 {
            firstName
            lastName
            slug
          }
          fighter2 {
            firstName
            lastName
            slug
          }
        }
      }
    }
  }
}
"""

FIGHT_ODDS_QUERY = """
query FightOddsQuery($fightSlug: String) {
  fightOfferTable(slug: $fightSlug) {
    slug
    bestOdds1
    bestOdds2
    fighter1 {
      firstName
      lastName
    }
    fighter2 {
      firstName
      lastName
    }
    straightOffers {
      edges {
        node {
          sportsbook {
            slug
            shortName
          }
          outcome1 {
            odds
            oddsOpen
          }
          outcome2 {
            odds
            oddsOpen
          }
        }
      }
    }
  }
}
"""
