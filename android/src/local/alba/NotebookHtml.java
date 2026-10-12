package local.alba;

import android.os.Build;
import android.text.Editable;
import android.text.Html;
import android.text.Spanned;
import android.text.SpannableStringBuilder;
import android.text.style.AbsoluteSizeSpan;
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Pixel-sized selections round-trip with the same HTML as the web notebook. */
final class NotebookHtml {
    private static final Pattern SPAN=Pattern.compile("<(/?)span\\b([^>]*)>",Pattern.CASE_INSENSITIVE);
    private static final Pattern STYLE=Pattern.compile("\\bstyle\\s*=\\s*([\"'])(.*?)\\1",Pattern.CASE_INSENSITIVE|Pattern.DOTALL);
    private static final Pattern SIZE=Pattern.compile("(?:^|;)\\s*font-size\\s*:\\s*(\\d+(?:\\.0+)?)px\\s*(?:;|$)",Pattern.CASE_INSENSITIVE);
    private static final class Start {final int size;Start(int value){size=value;}}

    static Spanned parse(String source){
        Matcher tags=SPAN.matcher(source);StringBuffer markup=new StringBuffer();ArrayDeque<Integer> sizes=new ArrayDeque<>();
        while(tags.find()){
            String replacement=tags.group();
            if(tags.group(1).isEmpty()){
                int size=0;Matcher style=STYLE.matcher(tags.group(2));
                if(style.find()){Matcher match=SIZE.matcher(style.group(2));if(match.find()){try{double value=Double.parseDouble(match.group(1));if(value>=8&&value<=72)size=(int)value;}catch(NumberFormatException ignored){}}}
                sizes.push(size);if(size>0)replacement+="<notetextsize"+size+">";
            }else if(!sizes.isEmpty()){
                int size=sizes.pop();if(size>0)replacement="</notetextsize"+size+">"+replacement;
            }
            tags.appendReplacement(markup,Matcher.quoteReplacement(replacement));
        }
        tags.appendTail(markup);
        Html.TagHandler handler=(opening,tag,text,reader)->{
            if(!tag.startsWith("notetextsize"))return;
            if(opening){try{int size=Integer.parseInt(tag.substring(12));if(size>=8&&size<=72)text.setSpan(new Start(size),text.length(),text.length(),Spanned.SPAN_MARK_MARK);}catch(NumberFormatException ignored){}}
            else{Start[] starts=text.getSpans(0,text.length(),Start.class);if(starts.length>0){Start start=starts[starts.length-1];int from=text.getSpanStart(start);text.removeSpan(start);if(from<text.length())text.setSpan(new AbsoluteSizeSpan(start.size,true),from,text.length(),Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);}}
        };
        Spanned parsed=Build.VERSION.SDK_INT>=24?Html.fromHtml(markup.toString(),Html.FROM_HTML_MODE_LEGACY,null,handler):Html.fromHtml(markup.toString(),null,handler);
        SpannableStringBuilder result=new SpannableStringBuilder(parsed);
        AbsoluteSizeSpan[] absolute=parsed.getSpans(0,parsed.length(),AbsoluteSizeSpan.class);
        Arrays.sort(absolute,(a,b)->Integer.compare(parsed.getSpanEnd(b)-parsed.getSpanStart(b),parsed.getSpanEnd(a)-parsed.getSpanStart(a)));
        // Explicit sizes override inherited heading styles; nested selections
        // apply after their outer size, matching the web notebook.
        for(AbsoluteSizeSpan span:absolute)result.removeSpan(span);
        for(AbsoluteSizeSpan span:absolute)result.setSpan(span,parsed.getSpanStart(span),parsed.getSpanEnd(span),Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        return result;
    }

    static String serialize(Spanned text){
        return Build.VERSION.SDK_INT>=24?Html.toHtml(text,Html.TO_HTML_PARAGRAPH_LINES_CONSECUTIVE):Html.toHtml(text);
    }

    static void setSize(Editable text,int start,int end,int size){
        if(start<0||end<=start||end>text.length()||size<8||size>72)throw new IllegalArgumentException("Invalid text selection or size");
        for(AbsoluteSizeSpan span:text.getSpans(start,end,AbsoluteSizeSpan.class)){
            int left=text.getSpanStart(span),right=text.getSpanEnd(span);
            if(right<=start||left>=end)continue;
            text.removeSpan(span);
            if(left<start)text.setSpan(new AbsoluteSizeSpan(span.getSize(),span.getDip()),left,start,Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
            if(right>end)text.setSpan(new AbsoluteSizeSpan(span.getSize(),span.getDip()),end,right,Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        }
        text.setSpan(new AbsoluteSizeSpan(size,true),start,end,Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
    }
}
