import { List, ListItem } from "@astryxdesign/core/List";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";

import { AppLink } from "@/components/AppLink";
import { LegalFooter } from "@/components/LegalFooter";
import { PageShell } from "@/components/PageShell";
import { SubpageHeader } from "@/components/SubpageHeader";
import { copy } from "@/i18n";
import { interpolate } from "@/i18n/interpolate";

const t = copy.terms;

export const metadata = { title: copy.legal.pageTitle(t.title) };

export default function TermsPage() {
  return (
    <PageShell
      contentWidth={640}
      padding={4}
      header={<SubpageHeader title={t.title} backHref="/login" />}
      footer={<LegalFooter />}
    >
      <VStack gap={6} paddingBlock={6}>
        <List hasDividers>
          {t.items.map((item) => (
            <ListItem key={item.term} label={<Text weight="semibold">{item.term}</Text>} description={<Text>{item.text}</Text>} />
          ))}
        </List>
        <Text as="p">
          {interpolate(t.seePrivacy, {
            privacy: (
              <AppLink key="privacy" href="/privacy">
                {copy.legal.privacy}
              </AppLink>
            ),
          })}
        </Text>
      </VStack>
    </PageShell>
  );
}
