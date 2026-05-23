"""GraphQL query strings for fightodds.io API."""

EVENT_CARD_LIST_QUERY = """
query EventCardListInfiniteScrollQuery(
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
  fight: fightBySlug(slug: $fightSlug) {
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
  fightOfferTable(slug: $fightSlug) {
    bestOdds1
    bestOdds2
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
